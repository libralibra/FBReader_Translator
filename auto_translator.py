import os
import zipfile
import pathlib
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List
import requests
import time
from deep_translator import GoogleTranslator, exceptions as TranslatorExceptions

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import sys
import io

# --- Backend Logic (Copied and slightly adapted from previous version) ---
# XMLHandler, Unpacker, Packer, translate_xml, download_file classes/functions
# ... (Insert the full backend code from the previous response here) ...
# --- Important Adaptations for GUI ---
# 1. Modify print statements if necessary, or rely on stdout redirection.
# 2. Ensure functions return clear success/failure indicators.
# 3. Potentially add progress reporting mechanisms if needed beyond simple logs.

# Example Adaptation: Make sure print works with redirection
class XMLHandler:
    """
    用于处理 XML 文件读取和写入的类。
    """
    XML_HEADER = '<?xml version="1.0" encoding="utf-8"?>\n'

    @staticmethod
    def read_entries(xml_file: str) -> Dict[str, str]:
        """
        从 XML 文件中读取词条。

        Args:
            xml_file: XML 文件路径。

        Returns:
            一个字典，键为词条的 name 属性，值为词条的文本内容。
            如果文件不存在或解析错误，返回空字典。
        """
        entries = {}
        try:
            # 使用健壮的解析器处理可能的实体和特殊字符
            parser = ET.XMLParser(encoding="utf-8")
            tree = ET.parse(xml_file, parser=parser)
            root = tree.getroot()
            for string_elem in root.findall('string'):
                name = string_elem.get('name')
                # 保留原始文本，包括潜在的 XML 实体（如 <, >, &)
                text_parts = []
                if string_elem.text:
                    text_parts.append(string_elem.text)
                for child in string_elem:
                     if child.tail:
                         text_parts.append(child.tail)

                text = "".join(text_parts).strip() # 合并并去除首尾空格

                if name is not None and text is not None:
                    entries[name] = text
        except FileNotFoundError:
             # Use print, which will be redirected
             print(f"Error: XML file not found at {xml_file}")
             return {}
        except ET.ParseError as e:
            print(f"Error parsing XML file {xml_file}: {e}")
            return {} # 返回空字典
        except Exception as e:
             print(f"An unexpected error occurred while reading {xml_file}: {e}")
             return {}
        return entries

    @staticmethod
    def write_entries(xml_file: str, entries: Dict[str, str]):
        """
        将词条写入 XML 文件。

        Args:
            xml_file: XML 文件路径。
            entries:  一个字典，键为词条的 name 属性，值为词条的文本内容。
        """
        root = ET.Element("resources")
        sorted_names = sorted(entries.keys())

        for name in sorted_names:
            text = entries[name]
            string_elem = ET.SubElement(root, "string")
            string_elem.set("name", name)
            string_elem.text = text

        try:
            xml_string = ET.tostring(root, encoding="unicode", method="xml") # 使用 unicode 获取字符串

            # 手动格式化以确保每个 string 元素占一行
            formatted_lines = [XMLHandler.XML_HEADER.strip()] # strip header initially
            in_resources = False
            current_indent = ""
            # Basic formatting
            xml_string_formatted = io.StringIO()
            xml_string_formatted.write(XMLHandler.XML_HEADER)
            xml_string_formatted.write('<resources>\n')
            indent = "    "
            for name in sorted_names:
                 text = entries[name]
                 # Basic escaping for XML within text if needed, ET usually handles this
                 # text = text.replace('&', '&').replace('<', '<').replace('>', '>')
                 xml_string_formatted.write(f'{indent}<string name="{name}">{text}</string>\n')
            xml_string_formatted.write('</resources>\n')


            # Ensure parent directory exists
            os.makedirs(os.path.dirname(xml_file), exist_ok=True) # 确保目录存在
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write(xml_string_formatted.getvalue())

        except Exception as e:
            print(f"Error writing XML file {xml_file}: {e}")
            raise # Re-raise for GUI to catch maybe

class Unpacker:
    """
    解压缩 ZIP 文件并将 XML 词条提取到单一 XML 文件的类。
    """

    def __init__(self, in_zip: Optional[str] = None, map_file: Optional[str] = None, out_xml: Optional[str] = None) -> None:
        self.in_zip = in_zip
        self.map_file = map_file
        self.out_xml = out_xml
        self.map_data: Dict[str, str] = {}  # 用于存储映射关系的字典
        self.extract_dir = None # 解压目录

    def unpack(self) -> bool:
        if not self.in_zip or not os.path.exists(self.in_zip):
            print(f"Error: Input ZIP file '{self.in_zip}' not found.")
            return False
        try:
            zip_path = pathlib.Path(self.in_zip)
            self.extract_dir = zip_path.parent / (zip_path.stem + "_extracted")
            self.extract_dir.mkdir(parents=True, exist_ok=True)
            print(f"Unpacking {self.in_zip} to {self.extract_dir}...")
            with zipfile.ZipFile(self.in_zip, 'r') as zip_ref:
                zip_ref.extractall(self.extract_dir)
            print(f"Successfully unpacked.")
            return True
        except zipfile.BadZipFile:
             print(f"Error: '{self.in_zip}' is not a valid ZIP file or is corrupted.")
             return False
        except Exception as e:
            print(f"Error unpacking ZIP file '{self.in_zip}': {e}")
            return False

    def flatten(self) -> bool:
        if not self.out_xml or not self.map_file:
            print("Error: Output XML file or map file path not specified.")
            return False
        if not self.extract_dir or not self.extract_dir.exists():
             print(f"Error: Extract directory '{self.extract_dir}' not found. Run unpack() first.")
             return False

        all_entries: Dict[str, str] = {}
        self.map_data = {}
        xml_files_found = 0

        print(f"Starting to flatten XML files from {self.extract_dir}...")
        for xml_file_path in self.extract_dir.rglob("*.xml"):
             if xml_file_path.is_file():
                xml_files_found += 1
                relative_path_str = str(xml_file_path.relative_to(self.extract_dir))
                entries = XMLHandler.read_entries(str(xml_file_path))
                if not entries:
                    print(f"Warning: No entries found or error reading {xml_file_path}. Skipping.")
                    continue
                for name, text in entries.items():
                    if name in all_entries and all_entries[name] != text:
                        original_location = self.map_data.get(name, "unknown")
                        print(f"Warning: Duplicate entry '{name}' in '{relative_path_str}'. "
                              f"Original in '{original_location}'. Overwriting.")
                    all_entries[name] = text
                    self.map_data[name] = relative_path_str

        if xml_files_found == 0:
             print(f"Warning: No XML files found in {self.extract_dir}.")

        print(f"Writing {len(all_entries)} entries to {self.out_xml}...")
        try:
            XMLHandler.write_entries(self.out_xml, all_entries)
        except Exception as e:
            print(f"Error writing flattened XML file '{self.out_xml}': {e}")
            return False

        print(f"Writing map file to {self.map_file}...")
        try:
            os.makedirs(os.path.dirname(self.map_file), exist_ok=True)
            with open(self.map_file, "w", encoding="utf-8") as f:
                for name in sorted(self.map_data.keys()):
                    xml_path = self.map_data[name]
                    f.write(f"{name}:{xml_path.replace(os.sep, '/')}\n")
        except Exception as e:
            print(f"Error writing map file '{self.map_file}': {e}")
            return False

        print(f"Successfully flattened {xml_files_found} XML files.")
        # Cleanup extracted dir? Optional.
        # import shutil
        # try:
        #     shutil.rmtree(self.extract_dir)
        #     print(f"Cleaned up temporary directory: {self.extract_dir}")
        # except Exception as e:
        #     print(f"Warning: Could not remove temporary directory '{self.extract_dir}': {e}")
        return True

    def read_map_file(self) -> bool:
        if not self.map_file:
            print("Error: Map file path not specified.")
            return False
        if not os.path.exists(self.map_file):
            print(f"Error: Map file '{self.map_file}' does not exist.")
            return False

        self.map_data = {}
        print(f"Reading map file from {self.map_file}...")
        try:
            with open(self.map_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line or ':' not in line:
                        if line: print(f"Warning: Skipping malformed line {i+1} in map file: '{line}'")
                        continue
                    try:
                        name, xml_path = line.split(":", 1)
                        self.map_data[name.strip()] = xml_path.strip()
                    except ValueError:
                         print(f"Warning: Skipping malformed line {i+1} (ValueError): '{line}'")
            print(f"Successfully read {len(self.map_data)} entries from map file.")
            return True
        except Exception as e:
            print(f"Error reading map file '{self.map_file}': {e}")
            return False

class Packer:
    """
    根据映射文件重建文件夹结构并将翻译后的 XML 词条打包成 ZIP 文件的类。
    """

    def __init__(self, in_xml: Optional[str] = None, map_file: Optional[str] = None, out_zip: Optional[str] = None) -> None:
        self.in_xml = in_xml
        self.map_file = map_file
        self.out_zip = out_zip
        self.map_data: Dict[str, str] = {}
        self.translated_entries: Dict[str, str] = {}
        self.target_lang_suffix = "zh"
        self.target_dir = None

    def set_target_language(self, lang_code: str = "zh", region_code: Optional[str] = None):
         self.target_lang_suffix = lang_code
         if region_code:
             region_suffix = f"r{region_code.upper()}"
             if lang_code.lower() == 'zh':
                 self.target_lang_suffix = f"{lang_code}-{region_suffix}"
             else:
                 self.target_lang_suffix = f"{lang_code}-{region_suffix}"
         print(f"Target language folder suffix set to: values-{self.target_lang_suffix}")

    def read_map_file(self) -> bool:
        unpacker_helper = Unpacker(map_file=self.map_file) # Use Unpacker's reader
        if unpacker_helper.read_map_file():
            self.map_data = unpacker_helper.map_data
            return True
        else:
            self.map_data = {}
            return False

    def read_translated_xml(self) -> bool:
        if not self.in_xml:
            print("Error: Input translated XML file path not specified.")
            return False
        if not os.path.exists(self.in_xml):
            print(f"Error: The input translated XML file '{self.in_xml}' does not exist.")
            return False

        print(f"Reading translated entries from {self.in_xml}...")
        self.translated_entries = XMLHandler.read_entries(self.in_xml)
        if not self.translated_entries and os.path.getsize(self.in_xml) > 0:
             print(f"Warning: No entries read from translated XML file '{self.in_xml}', but file is not empty. Check format.")
        elif not self.translated_entries:
             print(f"Info: Translated XML file '{self.in_xml}' appears to be empty or contains no <string> entries.")
        print(f"Read {len(self.translated_entries)} translated entries.")
        return True


    def generate(self) -> bool:
        if not self.in_xml or not self.map_file:
            print("Error: Input translated XML or map file path not specified.")
            return False
        if not self.read_map_file() or not self.read_translated_xml():
             print("Error: Failed to read map file or translated XML. Aborting generation.")
             return False
        if not self.map_data:
             print("Error: Map data is empty. Cannot generate structure.")
             return False

        # Use out_zip's directory for the temp folder
        if not self.out_zip:
             print("Error: Output ZIP path not specified for generating structure.")
             return False
        self.target_dir = pathlib.Path(self.out_zip).parent / "translated_temp"
        self.target_dir.mkdir(parents=True, exist_ok=True)
        print(f"Generating translated structure in temporary directory: {self.target_dir}")

        file_to_entries: Dict[str, Dict[str, str]] = {}
        missing_translations = 0
        processed_entries = 0

        for name, original_relative_path_str in self.map_data.items():
            original_relative_path = pathlib.Path(original_relative_path_str)
            original_filename = original_relative_path.name
            original_parent_dir = original_relative_path.parent

            target_parent_parts = []
            found_values_dir = False
            for part in original_parent_dir.parts:
                if part.startswith("values"):
                    target_parent_parts.append(f"values-{self.target_lang_suffix}")
                    found_values_dir = True
                else:
                    target_parent_parts.append(part)

            if not found_values_dir:
                 print(f"Warning: No 'values[-...]' dir in path '{original_relative_path_str}' for '{name}'. Using original structure.")

            target_relative_path = pathlib.Path(*target_parent_parts) / original_filename
            target_file_full_path = self.target_dir / target_relative_path
            target_file_key = str(target_file_full_path)

            if name in self.translated_entries:
                 processed_entries += 1
                 translated_text = self.translated_entries[name]
                 if target_file_key not in file_to_entries:
                     file_to_entries[target_file_key] = {}
                 file_to_entries[target_file_key][name] = translated_text
            else:
                 missing_translations += 1

        if missing_translations > 0:
             print(f"Warning: {missing_translations} entries from map file had no translation.")
        if processed_entries == 0 and len(self.map_data) > 0:
             print(f"Warning: Processed 0 entries for structure generation, though map file had {len(self.map_data)} entries.")


        print(f"Writing {len(file_to_entries)} translated XML files...")
        file_write_errors = 0
        for target_file_path_str, entries_dict in file_to_entries.items():
             try:
                 XMLHandler.write_entries(target_file_path_str, entries_dict)
             except Exception as e:
                 print(f"Error writing to file '{target_file_path_str}': {e}")
                 file_write_errors += 1

        if file_write_errors > 0:
            print(f"Error: Failed to write {file_write_errors} XML files.")
            # Optionally clean up self.target_dir here if desired on failure
            return False
        else:
            print(f"Successfully generated translated directory structure in {self.target_dir}")
            return True


    def pack(self) -> bool:
        if not self.out_zip:
            print("Error: Output ZIP file path not specified.")
            return False
        if not self.target_dir or not self.target_dir.exists():
            # Check if the dir is empty but exists
            if self.target_dir and self.target_dir.exists() and not any(self.target_dir.iterdir()):
                 print(f"Warning: Temporary directory '{self.target_dir}' exists but is empty. Packing will result in an empty zip.")
            else:
                print(f"Error: Temporary directory '{self.target_dir}' not found or inaccessible. Run generate() first.")
                return False

        print(f"Packing files from {self.target_dir} into {self.out_zip}...")
        files_packed = 0
        try:
            pathlib.Path(self.out_zip).parent.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(self.out_zip, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for file_path in self.target_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(self.target_dir)
                        zip_ref.write(file_path, arcname)
                        files_packed += 1

            print(f"Successfully packed {files_packed} files to {self.out_zip}")
            # Optional: Cleanup after successful packing
            import shutil
            try:
                shutil.rmtree(self.target_dir)
                print(f"Removed temporary directory: {self.target_dir}")
            except Exception as e:
                print(f"Warning: Could not remove temporary directory '{self.target_dir}': {e}")
            return True

        except Exception as e:
            print(f"Error packing ZIP file '{self.out_zip}': {e}")
            return False

def download_file(url: str, destination: str, progress_callback=None) -> bool:
    """ Downloads with optional progress reporting """
    print(f"Attempting to download file from {url} to {destination}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, stream=True, headers=headers, timeout=60)
        response.raise_for_status()

        pathlib.Path(destination).parent.mkdir(parents=True, exist_ok=True)

        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded_size = 0

        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=block_size):
                 if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if progress_callback and total_size > 0:
                        progress = int(100 * downloaded_size / total_size)
                        progress_callback(progress, downloaded_size, total_size)
                    elif progress_callback: # Handle case where total_size is 0
                         progress_callback(-1, downloaded_size, total_size) # Indicate indeterminate progress

        print(f"\nDownload complete.")
        if progress_callback: progress_callback(100, downloaded_size, total_size) # Ensure 100% is sent
        return True

    except requests.exceptions.RequestException as e:
        print(f"\nError downloading file: {e}")
        if progress_callback: progress_callback(-2, 0, 0) # Indicate error
        return False
    except Exception as e:
        print(f"\nAn unexpected error occurred during download: {e}")
        if progress_callback: progress_callback(-2, 0, 0) # Indicate error
        return False


def translate_xml(source_xml: str, target_xml: str, target_language: str = 'zh-CN', source_language: str = 'en', progress_callback=None, stop_event=None) -> bool:
    """ Translates XML with progress and stop capability """
    print(f"Starting translation from '{source_xml}' to '{target_xml}' (Lang: {target_language})...")
    if not os.path.exists(source_xml):
        print(f"Error: Source XML file '{source_xml}' not found.")
        if progress_callback: progress_callback(-2) # Error state
        return False

    source_entries = XMLHandler.read_entries(source_xml)
    if not source_entries:
        print("Warning: No entries found in source XML. Creating an empty target file.")
        try:
             XMLHandler.write_entries(target_xml, {})
             if progress_callback: progress_callback(100) # Task complete (even if empty)
             return True
        except Exception as e:
             print(f"Error creating empty target XML file '{target_xml}': {e}")
             if progress_callback: progress_callback(-2) # Error state
             return False

    try:
        # Use language code before hyphen for deep-translator if applicable
        translator_target_lang = target_language.split('-')[0]
        translator = GoogleTranslator(source=source_language, target=translator_target_lang)
        print(f"Using translator: Source='{source_language}', Target='{translator_target_lang}'")
    except Exception as e:
        print(f"Error initializing translator: {e}")
        if progress_callback: progress_callback(-2) # Error state
        return False

    translated_entries: Dict[str, str] = {}
    total_entries = len(source_entries)
    translated_count = 0
    error_count = 0
    print(f"Translating {total_entries} entries...")

    for i, (name, text) in enumerate(source_entries.items()):
        # Check if stop requested
        if stop_event and stop_event.is_set():
             print("\nTranslation cancelled by user.")
             if progress_callback: progress_callback(-3) # Cancelled state
             return False # Indicate not fully completed

        progress = int(100 * (i + 1) / total_entries) if total_entries > 0 else 0
        if progress_callback:
            progress_callback(progress)

        if not text or text.isspace():
            # print(f"Skipping empty entry: '{name}'") # Reduce log noise
            translated_entries[name] = text
            translated_count += 1
            continue

        try:
            translated_text = translator.translate(text)
            if translated_text is not None: # Allow empty string as valid translation
                translated_entries[name] = translated_text
                translated_count += 1
                # print(f"'{name}' translated.") # Reduce log noise
            else:
                 print(f"\nWarning: Translation returned None for name '{name}', original: '{text[:50]}...'")
                 translated_entries[name] = text # Keep original
                 error_count += 1

            # Add delay - crucial for free tier
            time.sleep(0.6) # Adjust as needed, maybe slightly longer

        except TranslatorExceptions.NotValidPayload as payload_err:
             error_count += 1
             print(f"\nError translating '{name}' (Payload): {payload_err}. Text length: {len(text)}. Skipping.")
             print(f"Original: {text[:100]}...") # Show beginning of problematic text
             translated_entries[name] = text # Keep original
        except TranslatorExceptions.TranslationNotFound as notfound_err:
             error_count += 1
             print(f"\nWarning: Translation not found for '{name}': {notfound_err}. Keeping original.")
             print(f"Original: {text[:100]}...")
             translated_entries[name] = text # Keep original
        except requests.exceptions.ConnectionError as conn_err:
             error_count += 1
             print(f"\nError translating '{name}' (Connection): {conn_err}. Check network. Keeping original.")
             translated_entries[name] = text
             time.sleep(5) # Longer pause after connection error
        except Exception as e:
            error_count += 1
            print(f"\nError translating entry '{name}': {type(e).__name__}: {e}")
            # print(f"Original text: {text}") # Optional: uncomment for debugging
            translated_entries[name] = text # Keep original
            # Maybe add longer delay or stop logic here if errors persist

    print("\nTranslation finished.")
    if error_count > 0:
         print(f"Warning: {error_count} entries encountered errors/warnings during translation.")
    if stop_event and stop_event.is_set(): # Check again after loop finishes naturally
         return False # Return False if cancelled during the process

    print(f"Writing {len(translated_entries)} translated entries to {target_xml}...")
    try:
        XMLHandler.write_entries(target_xml, translated_entries)
        print("Successfully wrote translated XML file.")
        if progress_callback: progress_callback(100) # Final confirmation
        return True
    except Exception as e:
        print(f"Error writing translated XML file '{target_xml}': {e}")
        if progress_callback: progress_callback(-2) # Error state
        return False

# --- GUI Code ---

class TextAreaRedirector:
    """ Redirects stdout to a Tkinter Text widget """
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.text_widget.config(state=tk.NORMAL) # Ensure it's writable at start

    def write(self, string):
        # Ensure updates happen in the main GUI thread
        self.text_widget.after(0, self._write_to_widget, string)

    def _write_to_widget(self, string):
        try:
            self.text_widget.insert(tk.END, string)
            self.text_widget.see(tk.END) # Auto-scroll
            self.text_widget.update_idletasks() # Process events to keep responsive
        except tk.TclError:
             # Handle cases where the widget might be destroyed
             pass

    def flush(self):
        # Tkinter Text widget doesn't need explicit flushing like a file
        pass

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("XML Translator Tool")
        # Make window resizable
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.main_frame.columnconfigure(1, weight=1) # Allow entry fields to expand

        # --- Variables ---
        self.in_zip_var = tk.StringVar()
        self.out_zip_var = tk.StringVar()
        self.map_file_var = tk.StringVar()
        self.flat_xml_var = tk.StringVar()
        self.trans_xml_var = tk.StringVar()
        self.lang_var = tk.StringVar()
        self.region_var = tk.StringVar()
        self.url_var = tk.StringVar()
        self.stop_event = None # threading.Event() for cancelling tasks

        # --- Language Options ---
        # Common languages supported by Google Translate (subset)
        self.languages = {
             "Chinese (Simplified)": "zh-CN", "Chinese (Traditional)": "zh-TW",
             "English": "en", "Spanish": "es", "French": "fr", "German": "de",
             "Japanese": "ja", "Korean": "ko", "Russian": "ru", "Portuguese": "pt",
             "Italian": "it", "Arabic": "ar", "Hindi": "hi"
        }
        self.lang_display_names = sorted(self.languages.keys())
        self.lang_var.set(self.lang_display_names[0]) # Default to first sorted name

        # --- GUI Elements ---
        row_index = 0

        # Download Section
        ttk.Label(self.main_frame, text="Download URL (Optional):").grid(row=row_index, column=0, sticky=tk.W, pady=2)
        self.url_entry = ttk.Entry(self.main_frame, textvariable=self.url_var, width=60)
        self.url_entry.grid(row=row_index, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.download_button = ttk.Button(self.main_frame, text="Download", command=self.run_download_thread)
        self.download_button.grid(row=row_index, column=2, sticky=tk.E, pady=2, padx=5)
        row_index += 1

        # Input ZIP
        ttk.Label(self.main_frame, text="Source ZIP File:").grid(row=row_index, column=0, sticky=tk.W, pady=2)
        self.in_zip_entry = ttk.Entry(self.main_frame, textvariable=self.in_zip_var, width=60)
        self.in_zip_entry.grid(row=row_index, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.in_zip_button = ttk.Button(self.main_frame, text="Browse...", command=self.browse_in_zip)
        self.in_zip_button.grid(row=row_index, column=2, sticky=tk.E, pady=2, padx=5)
        row_index += 1

        # Output ZIP
        ttk.Label(self.main_frame, text="Output ZIP File:").grid(row=row_index, column=0, sticky=tk.W, pady=2)
        self.out_zip_entry = ttk.Entry(self.main_frame, textvariable=self.out_zip_var, width=60)
        self.out_zip_entry.grid(row=row_index, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.out_zip_button = ttk.Button(self.main_frame, text="Save As...", command=self.browse_out_zip)
        self.out_zip_button.grid(row=row_index, column=2, sticky=tk.E, pady=2, padx=5)
        row_index += 1

        # Intermediate Files Frame
        int_frame = ttk.LabelFrame(self.main_frame, text="Intermediate Files", padding="5")
        int_frame.grid(row=row_index, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        int_frame.columnconfigure(1, weight=1)

        ttk.Label(int_frame, text="Map File:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.map_file_entry = ttk.Entry(int_frame, textvariable=self.map_file_var, width=50)
        self.map_file_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        # ttk.Button(int_frame, text="...", width=3).grid(row=0, column=2, sticky=tk.E, pady=2, padx=2) # Optional browse

        ttk.Label(int_frame, text="Flattened XML:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.flat_xml_entry = ttk.Entry(int_frame, textvariable=self.flat_xml_var, width=50)
        self.flat_xml_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        # ttk.Button(int_frame, text="...", width=3).grid(row=1, column=2, sticky=tk.E, pady=2, padx=2)

        ttk.Label(int_frame, text="Translated XML:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.trans_xml_entry = ttk.Entry(int_frame, textvariable=self.trans_xml_var, width=50)
        self.trans_xml_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        # ttk.Button(int_frame, text="...", width=3).grid(row=2, column=2, sticky=tk.E, pady=2, padx=2)

        row_index += 1


        # Language Selection Frame
        lang_frame = ttk.LabelFrame(self.main_frame, text="Translation Settings", padding="5")
        lang_frame.grid(row=row_index, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        lang_frame.columnconfigure(1, weight=1)
        lang_frame.columnconfigure(3, weight=1)

        ttk.Label(lang_frame, text="Target Language:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.lang_combo = ttk.Combobox(lang_frame, textvariable=self.lang_var, values=self.lang_display_names, state="readonly", width=20)
        self.lang_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        ttk.Label(lang_frame, text="Region (e.g., CN, TW, US):").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.region_entry = ttk.Entry(lang_frame, textvariable=self.region_var, width=10)
        self.region_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=2)

        row_index += 1

        # --- Action Buttons ---
        action_frame = ttk.Frame(self.main_frame, padding="5")
        action_frame.grid(row=row_index, column=0, columnspan=3, pady=10)

        self.unpack_button = ttk.Button(action_frame, text="1. Unpack & Flatten", command=self.run_unpack_flatten_thread)
        self.unpack_button.pack(side=tk.LEFT, padx=5)

        self.translate_button = ttk.Button(action_frame, text="2. Translate", command=self.run_translate_thread)
        self.translate_button.pack(side=tk.LEFT, padx=5)

        self.pack_button = ttk.Button(action_frame, text="3. Reconstruct & Pack", command=self.run_pack_thread)
        self.pack_button.pack(side=tk.LEFT, padx=5)

        self.run_all_button = ttk.Button(action_frame, text="Run All Steps", command=self.run_all_steps_thread)
        self.run_all_button.pack(side=tk.LEFT, padx=15)

        self.cancel_button = ttk.Button(action_frame, text="Cancel Task", command=self.cancel_task, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=5)


        row_index += 1

        # --- Progress Bar ---
        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(self.main_frame, orient="horizontal", length=300, mode="determinate", variable=self.progress_var)
        self.progress_bar.grid(row=row_index, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row_index += 1


        # --- Log Area ---
        ttk.Label(self.main_frame, text="Log Output:").grid(row=row_index, column=0, sticky=tk.W, pady=(5,0))
        row_index += 1
        self.log_area = scrolledtext.ScrolledText(self.main_frame, wrap=tk.WORD, height=15, width=80, state=tk.DISABLED)
        self.log_area.grid(row=row_index, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        # Allow log area to expand
        self.main_frame.rowconfigure(row_index, weight=1)

        # Redirect stdout
        self.redirector = TextAreaRedirector(self.log_area)
        sys.stdout = self.redirector
        sys.stderr = self.redirector # Redirect errors too

        # Bind path changes to update defaults
        self.in_zip_var.trace_add("write", self.update_default_paths)
        self.out_zip_var.trace_add("write", self.update_default_paths)


    def update_default_paths(self, *args):
        """ Update intermediate file paths based on input/output zip """
        in_zip_path = self.in_zip_var.get()
        out_zip_path_str = self.out_zip_var.get()

        if in_zip_path:
            in_path = pathlib.Path(in_zip_path)
            # Use output dir if specified, else input dir
            base_dir = pathlib.Path(out_zip_path_str).parent if out_zip_path_str else in_path.parent
            base_name = in_path.stem

            # Only update if the fields are empty or seem to be defaults from a *different* base name
            current_map = self.map_file_var.get()
            current_flat = self.flat_xml_var.get()
            current_trans = self.trans_xml_var.get()

            map_default = base_dir / f"{base_name}_map.txt"
            flat_default = base_dir / f"{base_name}_flat.xml"
            trans_default = base_dir / f"{base_name}_translated.xml"

            if not current_map or "_map.txt" in current_map:
                 self.map_file_var.set(str(map_default))
            if not current_flat or "_flat.xml" in current_flat:
                 self.flat_xml_var.set(str(flat_default))
            if not current_trans or "_translated.xml" in current_trans:
                 self.trans_xml_var.set(str(trans_default))

    # --- Browse Functions ---
    def browse_in_zip(self):
        filepath = filedialog.askopenfilename(
            title="Select Source ZIP File",
            filetypes=(("ZIP files", "*.zip"), ("All files", "*.*"))
        )
        if filepath:
            self.in_zip_var.set(filepath)
            # Try to set a default output path
            if not self.out_zip_var.get():
                 p = pathlib.Path(filepath)
                 default_out = p.parent / f"{p.stem}_translated.zip"
                 self.out_zip_var.set(str(default_out))
            self.update_default_paths() # Trigger intermediate updates


    def browse_out_zip(self):
        filepath = filedialog.asksaveasfilename(
            title="Save Output ZIP File As",
            defaultextension=".zip",
            filetypes=(("ZIP files", "*.zip"), ("All files", "*.*"))
        )
        if filepath:
            self.out_zip_var.set(filepath)
            self.update_default_paths() # Trigger intermediate updates

    # --- Task Execution (using Threads) ---

    def set_ui_state(self, state):
        """ Enable/Disable buttons. state=tk.NORMAL or tk.DISABLED """
        self.download_button.config(state=state)
        self.unpack_button.config(state=state)
        self.translate_button.config(state=state)
        self.pack_button.config(state=state)
        self.run_all_button.config(state=state)
        # Enable cancel button only when a task is running
        self.cancel_button.config(state=tk.NORMAL if state == tk.DISABLED else tk.DISABLED)
        # Prevent changing paths during operation
        self.in_zip_button.config(state=state)
        self.out_zip_button.config(state=state)
        self.in_zip_entry.config(state=state)
        self.out_zip_entry.config(state=state)
        # Maybe disable intermediate path entries too?
        # self.map_file_entry.config(state=state)
        # ... etc.

    def clear_log(self):
         self.log_area.config(state=tk.NORMAL)
         self.log_area.delete(1.0, tk.END)
         self.log_area.config(state=tk.DISABLED)

    def log_message(self, message):
         # Helper to add message even if stdout redirection fails
         self.log_area.config(state=tk.NORMAL)
         self.log_area.insert(tk.END, message + "\n")
         self.log_area.see(tk.END)
         self.log_area.config(state=tk.DISABLED)
         self.log_area.update_idletasks()


    def update_progress(self, value, current_size=None, total_size=None):
         """ Callback for progress updates, run in main thread """
         if value == -1: # Indeterminate download
             mode = "indeterminate"
             self.progress_bar.config(mode=mode)
             self.progress_bar.start(10)
             # Optionally update log with downloaded size
             if current_size is not None:
                  size_mb = current_size / (1024*1024)
                  self.log_message(f"\rDownloaded: {size_mb:.2f} MB", ) # Use \r? Maybe not in text area
         elif value == -2: # Error
              self.progress_bar.stop()
              self.progress_bar.config(mode="determinate", value=0)
              self.log_message("An error occurred.")
         elif value == -3: # Cancelled
              self.progress_bar.stop()
              self.progress_bar.config(mode="determinate", value=0)
              self.log_message("Task cancelled.")
         else: # Normal progress or completion
             self.progress_bar.stop() # Stop indeterminate if it was running
             self.progress_bar.config(mode="determinate", value=value)
             # Optionally show download size on completion
             if value == 100 and current_size is not None and total_size is not None:
                  size_mb = current_size / (1024*1024)
                  total_mb = total_size / (1024*1024)
                  # Update log without newline for final size
                  # self.log_message(f"Downloaded: {size_mb:.2f} MB / {total_mb:.2f} MB")
         self.root.update_idletasks() # Ensure GUI updates progress bar visually


    def run_task_in_thread(self, task_func, *args):
        """ Generic function to run a task in a thread """
        self.clear_log()
        self.set_ui_state(tk.DISABLED)
        self.progress_var.set(0)
        self.stop_event = threading.Event() # Create a new event for this task

        # Pass the stop_event and progress callback to the target function if it accepts them
        thread_args = list(args)
        # Check if task_func expects 'progress_callback' and 'stop_event' keyword arguments
        # This is a bit simplistic, relies on naming convention in backend functions
        import inspect
        sig = inspect.signature(task_func)
        if 'progress_callback' in sig.parameters:
            thread_args.append(lambda v, c=None, t=None: self.root.after(0, self.update_progress, v, c, t))
        if 'stop_event' in sig.parameters:
             thread_args.append(self.stop_event)


        thread = threading.Thread(target=self._thread_wrapper, args=(task_func, thread_args), daemon=True)
        thread.start()

    def _thread_wrapper(self, task_func, args):
        """ Wraps the task execution and UI state restoration """
        success = False
        try:
            # sys.stdout = self.redirector # Ensure redirection in thread if needed (might cause issues)
            # sys.stderr = self.redirector
            print(f"Starting task: {task_func.__name__}...")
            success = task_func(*args)
            if success:
                print(f"Task '{task_func.__name__}' completed successfully.")
            else:
                 # Check if cancelled
                 if self.stop_event and self.stop_event.is_set():
                      print(f"Task '{task_func.__name__}' was cancelled.")
                 else:
                      print(f"Task '{task_func.__name__}' failed or returned False.")
        except Exception as e:
            print(f"\n!!! EXCEPTION during task '{task_func.__name__}' !!!")
            print(f"{type(e).__name__}: {e}")
            import traceback
            print(traceback.format_exc())
            success = False
        finally:
            # Ensure UI update happens in the main thread
            self.root.after(0, self.set_ui_state, tk.NORMAL)
            self.root.after(0, self.progress_bar.stop) # Stop indeterminate progress if running
            # Set progress to 100 if successful, 0 otherwise (unless cancelled)
            final_progress = 100 if success else 0
            if self.stop_event and self.stop_event.is_set():
                 final_progress = self.progress_var.get() # Keep current progress on cancel
            self.root.after(0, self.update_progress, final_progress)
            self.stop_event = None # Clear the event

    def cancel_task(self):
         if self.stop_event:
              print("\n--- Sending cancel request ---")
              self.stop_event.set()
              self.cancel_button.config(state=tk.DISABLED) # Disable after requesting

    # --- Specific Task Runners ---

    def run_download_thread(self):
         url = self.url_var.get()
         if not url:
             messagebox.showerror("Error", "Please enter a download URL.")
             return

         dest_path = filedialog.asksaveasfilename(
            title="Save Downloaded File As",
            defaultextension=".zip",
            filetypes=(("ZIP files", "*.zip"), ("All files", "*.*"))
         )
         if not dest_path:
             return

         # Set the input zip var after successful download?
         self.run_task_in_thread(self._download_and_set_input, url, dest_path)

    def _download_and_set_input(self, url, dest_path, progress_callback=None, stop_event=None):
         # Wrapper to call download and update input path
         # Note: download_file needs adaptation to accept stop_event if cancellable download is needed
         success = download_file(url, dest_path, progress_callback=progress_callback)
         if success:
              self.root.after(0, self.in_zip_var.set, dest_path) # Update GUI in main thread
         return success

    def run_unpack_flatten_thread(self):
        in_zip = self.in_zip_var.get()
        map_file = self.map_file_var.get()
        flat_xml = self.flat_xml_var.get()
        if not all([in_zip, map_file, flat_xml]):
            messagebox.showerror("Error", "Please specify Input ZIP, Map File, and Flattened XML paths.")
            return
        self.run_task_in_thread(self._unpack_and_flatten, in_zip, map_file, flat_xml)

    def _unpack_and_flatten(self, in_zip, map_file, flat_xml, progress_callback=None, stop_event=None):
        # Note: Unpack/Flatten are usually fast, progress might be overkill
        # but we can update it stepwise. stop_event isn't implemented in backend here.
        unpacker = Unpacker(in_zip=in_zip, map_file=map_file, out_xml=flat_xml)
        if progress_callback: self.root.after(0, progress_callback, 10) # Small progress
        if unpacker.unpack():
            if progress_callback: self.root.after(0, progress_callback, 50)
            if unpacker.flatten():
                 if progress_callback: self.root.after(0, progress_callback, 100)
                 return True
        return False

    def run_translate_thread(self):
        flat_xml = self.flat_xml_var.get()
        trans_xml = self.trans_xml_var.get()
        lang_display = self.lang_var.get()
        target_lang_code = self.languages.get(lang_display, 'zh-CN') # Get code like 'zh-CN'

        if not all([flat_xml, trans_xml, target_lang_code]):
            messagebox.showerror("Error", "Please specify Flattened XML, Translated XML paths and select a language.")
            return
        self.run_task_in_thread(translate_xml, flat_xml, trans_xml, target_lang_code, 'en') # Pass progress/stop implicitly via wrapper

    def run_pack_thread(self):
        trans_xml = self.trans_xml_var.get()
        map_file = self.map_file_var.get()
        out_zip = self.out_zip_var.get()
        lang_display = self.lang_var.get()
        target_lang_code_full = self.languages.get(lang_display, 'zh-CN') # e.g., zh-CN
        region = self.region_var.get().strip().upper() # e.g., CN

        # Extract base lang code (e.g., 'zh' from 'zh-CN')
        target_lang_code_base = target_lang_code_full.split('-')[0]
        # Use specified region if provided, else try from full code, else None
        target_region_code = region if region else (target_lang_code_full.split('-')[1] if '-' in target_lang_code_full else None)


        if not all([trans_xml, map_file, out_zip]):
            messagebox.showerror("Error", "Please specify Translated XML, Map File, and Output ZIP paths.")
            return

        self.run_task_in_thread(self._reconstruct_and_pack, trans_xml, map_file, out_zip, target_lang_code_base, target_region_code)

    def _reconstruct_and_pack(self, trans_xml, map_file, out_zip, lang_code, region_code, progress_callback=None, stop_event=None):
         # stop_event not implemented in backend packer functions
         packer = Packer(in_xml=trans_xml, map_file=map_file, out_zip=out_zip)
         packer.set_target_language(lang_code=lang_code, region_code=region_code)
         if progress_callback: self.root.after(0, progress_callback, 10)
         if packer.generate():
             if progress_callback: self.root.after(0, progress_callback, 50)
             if packer.pack():
                  if progress_callback: self.root.after(0, progress_callback, 100)
                  return True
         return False

    def run_all_steps_thread(self):
         # Confirmation dialog?
         if not messagebox.askyesno("Confirm Run All", "This will execute all steps: Unpack, Translate, and Pack.\nEnsure all paths and settings are correct.\n\nContinue?"):
              return

         # Get all params once
         in_zip = self.in_zip_var.get()
         map_file = self.map_file_var.get()
         flat_xml = self.flat_xml_var.get()
         trans_xml = self.trans_xml_var.get()
         out_zip = self.out_zip_var.get()
         lang_display = self.lang_var.get()
         target_lang_code_full = self.languages.get(lang_display, 'zh-CN')
         region = self.region_var.get().strip().upper()
         target_lang_code_base = target_lang_code_full.split('-')[0]
         target_region_code = region if region else (target_lang_code_full.split('-')[1] if '-' in target_lang_code_full else None)

         if not all([in_zip, map_file, flat_xml, trans_xml, out_zip, target_lang_code_full]):
             messagebox.showerror("Error", "Please ensure all file paths and language settings are specified correctly before running all steps.")
             return

         # Run the combined task in a thread
         self.run_task_in_thread(self._run_all_steps_task,
                                 in_zip, map_file, flat_xml, trans_xml, out_zip,
                                 target_lang_code_full, target_lang_code_base, target_region_code)

    def _run_all_steps_task(self, in_zip, map_file, flat_xml, trans_xml, out_zip,
                           target_lang_full, target_lang_base, target_region,
                           progress_callback=None, stop_event=None):
        """ The actual task performing all steps sequentially """
        total_steps = 3 # Unpack/Flatten, Translate, Pack

        def update_overall_progress(step, step_progress):
             # Calculate overall progress based on current step and its progress
             overall = int(((step - 1) * 100 + step_progress) / total_steps)
             if progress_callback:
                  self.root.after(0, progress_callback, overall) # Update GUI from main thread


        # --- Step 1: Unpack & Flatten ---
        print("\n--- Starting Step 1: Unpack & Flatten ---")
        update_overall_progress(1, 0)
        step1_success = self._unpack_and_flatten(in_zip, map_file, flat_xml,
                                                 progress_callback=lambda p: update_overall_progress(1, p),
                                                 stop_event=stop_event)
        if not step1_success or (stop_event and stop_event.is_set()):
            print("Step 1 failed or cancelled.")
            return False
        update_overall_progress(1, 100) # Ensure step 1 shows 100%

        # --- Step 2: Translate ---
        print("\n--- Starting Step 2: Translate ---")
        update_overall_progress(2, 0)
        # Need a wrapper for translate_xml's progress callback to fit update_overall_progress
        def translate_progress_wrapper(progress):
             update_overall_progress(2, progress if progress >= 0 else 0) # Use 0 for error/cancel states in overall %
             if progress == -2: print("Translation Error occurred.")
             if progress == -3: print("Translation Cancelled.")

        step2_success = translate_xml(flat_xml, trans_xml, target_lang_full, 'en',
                                      progress_callback=translate_progress_wrapper,
                                      stop_event=stop_event)
        if not step2_success or (stop_event and stop_event.is_set()):
            print("Step 2 failed or cancelled.")
            return False
        update_overall_progress(2, 100) # Ensure step 2 shows 100%

        # --- Step 3: Reconstruct & Pack ---
        print("\n--- Starting Step 3: Reconstruct & Pack ---")
        update_overall_progress(3, 0)
        step3_success = self._reconstruct_and_pack(trans_xml, map_file, out_zip, target_lang_base, target_region,
                                                   progress_callback=lambda p: update_overall_progress(3, p),
                                                   stop_event=stop_event)
        if not step3_success or (stop_event and stop_event.is_set()):
            print("Step 3 failed or cancelled.")
            return False
        update_overall_progress(3, 100) # Ensure step 3 shows 100% / Overall 100%

        print("\n--- All steps completed successfully! ---")
        return True


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()

    # Restore stdout/stderr after GUI closes (optional)
    sys.stdout = sys.__stdout__