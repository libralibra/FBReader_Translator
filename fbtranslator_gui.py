import sys
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import threading
from fbtranslator import *

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

class XMLZipTranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("XML Translator Tool")
        # Make window resizable
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # ============ variables ============
        self.url = tk.StringVar(value=r'https://fbreader.org/static/strings/android/en.zip')
        self.in_zip = tk.StringVar()
        self.out_zip = tk.StringVar()
        self.map_file = tk.StringVar()
        self.en_xml = tk.StringVar()
        self.out_xml = tk.StringVar()
        self.des_lang = tk.StringVar(value="zh")
        self.stop_event = None # threading.Event() for cancelling tasks
        
        # create UI
        self.create_widgets()
    
    def create_widgets(self):
        # define the main frame
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.main_frame.columnconfigure(1, weight=1) # Allow entry fields to expand
        
        # ============ UI Elements ============
        row_index = 0

        # source file Frame
        src_frame = ttk.LabelFrame(self.main_frame, text="Source Files", padding="5")
        src_frame.grid(row=row_index, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        src_frame.columnconfigure(1, weight=1)

        # download zip
        ttk.Label(src_frame, text="Download URL (Optional):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.url_entry = ttk.Entry(src_frame, textvariable=self.url, width=60)
        self.url_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.download_button = ttk.Button(src_frame, text="Download", command=self.download_zip_callback)
        self.download_button.grid(row=0, column=2,sticky=tk.E, pady=2, padx=5)

        # input zip (the downloaded one)
        ttk.Label(src_frame, text="Source ZIP File:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.in_zip_entry = ttk.Entry(src_frame, textvariable=self.in_zip, width=60)
        self.in_zip_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.in_zip_button = ttk.Button(src_frame, text="Browse...", command=self.browse_zip)
        self.in_zip_button.grid(row=1, column=2, sticky=tk.E, pady=2, padx=5)

        # flattened xml
        ttk.Label(src_frame, text="Flattened XML:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.flatten_xml_entry = ttk.Entry(src_frame, textvariable=self.en_xml, width=60)
        self.flatten_xml_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.flatten_xml_button = ttk.Button(src_frame, text="Save As...", command=self.browse_flatten_xml)
        self.flatten_xml_button.grid(row=2, column=2, sticky=tk.E, pady=2, padx=5)

        # map file
        ttk.Label(src_frame, text="Mapping XML:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.map_file_entry = ttk.Entry(src_frame, textvariable=self.map_file, width=60)
        self.map_file_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.map_file_button = ttk.Button(src_frame, text="Browse...", command=self.browse_map)
        self.map_file_button.grid(row=3, column=2, sticky=tk.E, pady=2, padx=5)

        row_index += 1

        # output file Frame
        des_frame = ttk.LabelFrame(self.main_frame, text="Target Files", padding="5")
        des_frame.grid(row=row_index, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        des_frame.columnconfigure(1, weight=1)

        # translated file 
        ttk.Label(des_frame, text="Translated XML:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.flatten_xml_entry = ttk.Entry(des_frame, textvariable=self.out_xml, width=50)
        self.flatten_xml_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.flatten_xml_button = ttk.Button(des_frame, text="Browse...", command=self.browse_translated_xml)
        self.flatten_xml_button.grid(row=0, column=2, sticky=tk.E, pady=2, padx=5)

        # output zip
        ttk.Label(des_frame, text="Output Zip:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.out_zip_entry = ttk.Entry(des_frame, textvariable=self.out_zip, width=60)
        self.out_zip_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=2, padx=5)
        self.out_zip_button = ttk.Button(des_frame, text="Save As...", command=self.save_zip)
        self.out_zip_button.grid(row=1, column=2,sticky=tk.E, pady=2, padx=5)

        row_index += 1

        # translation Frame
        lang_frame = ttk.LabelFrame(self.main_frame, text="Translation Settings", padding="5")
        lang_frame.grid(row=row_index, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        lang_frame.columnconfigure(1, weight=1)
        # lang_frame.columnconfigure(3, weight=1)

        # language list
        # Common languages supported by Google Translate (subset)
        self.languages = {
             "Chinese (Simplified)": "zh", "Chinese (Traditional)": "zh-TW",
             "English": "en", "Spanish": "es", "French": "fr", "German": "de",
             "Japanese": "ja", "Korean": "ko", "Russian": "ru", "Portuguese": "pt",
             "Italian": "it"
        }
        self.lang_display_names = sorted(self.languages.keys())
        self.des_lang.set(self.lang_display_names[0]) # Default to first sorted name

        ttk.Label(lang_frame, text="Target Language:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.lang_combo = ttk.Combobox(lang_frame, textvariable=self.des_lang, values=self.lang_display_names, state="readonly", width=20)
        self.lang_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        row_index += 1

        # action buttons
        action_frame = ttk.Frame(self.main_frame, padding="5")
        action_frame.grid(row=row_index, column=0, columnspan=3, pady=10)

        self.unpack_button = ttk.Button(action_frame, text="1. Unpack & Flatten", command=self.unpack_zip)
        self.unpack_button.pack(side=tk.LEFT, padx=5)

        self.translate_button = ttk.Button(action_frame, text="2. Translate", state="disabled")
        self.translate_button.pack(side=tk.LEFT, padx=5)

        self.pack_button = ttk.Button(action_frame, text="3. Reconstruct & Pack", command=self.reconstruct_pack)
        self.pack_button.pack(side=tk.LEFT, padx=5)

        self.run_all_button = ttk.Button(action_frame, text="Run All Steps", command=self.run_all_steps)
        self.run_all_button.pack(side=tk.LEFT, padx=15)

        self.cancel_button = ttk.Button(action_frame, text="Cancel Task", command=self.cancel_task, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=5)

        row_index += 1

        # --- Progress Bar ---
        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(self.main_frame, orient="horizontal", length=400, mode="determinate", variable=self.progress_var)
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
    
    def cancel_task(self):
         if self.stop_event:
              self.log("\n--- Sending cancel request ---")
              self.stop_event.set()
              self.cancel_button.config(state=tk.DISABLED) # Disable after requesting
    
    def download_zip_callback(self):
        url = self.url.get()
        if not url:
            self.warn('please enter a URL to download the ZIP file')
            messagebox.showerror("Error", "Please enter a URL to download the ZIP file.")
            return
        
        save_path = filedialog.asksaveasfilename(
            title="Save Downloaded File As:",
            defaultextension=".zip", 
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")])
        if not save_path:
            self.warn('download path was not defined')
            return
        
        self.info(f'downloading zip file {save_path}')
        success = download_zip(url, save_path)
        if success:
            self.in_zip.set(save_path)  # update the in zip path
            self.info(f'zip file downloaded as {self.in_zip.get()}')
        else:
            self.error(f'error while downloading {self.url.get()}')

    def browse_zip(self):
        in_zip = filedialog.askopenfilename(filetypes=[("ZIP files", "*.zip")])
        if in_zip and not in_zip.lower().endswith(".zip"):
            in_zip += ".zip"
        self.in_zip.set(in_zip)
        if in_zip:
            self.info(f'source zip defined {in_zip}')
    
    def save_zip(self):
        out_zip = filedialog.asksaveasfilename(filetypes=[("ZIP files", "*.zip")])
        if out_zip and not out_zip.lower().endswith(".zip"):
            out_zip += ".zip"
        self.out_zip.set(out_zip)
        if out_zip:
            self.info(f'output zip defined {out_zip}')
    
    def browse_map(self):
        self.map_file.set(filedialog.asksaveasfilename(filetypes=[("No extension", "")]))
        if self.map_file.get():
            self.info(f'mapping file defined {self.map_file.get()}')
    
    def browse_flatten_xml(self):
        en_xml = filedialog.asksaveasfilename(filetypes=[("XML files", "*.xml")])
        if en_xml and not en_xml.lower().endswith(".xml"):
            en_xml += ".xml"
        self.en_xml.set(en_xml)
        if en_xml:
            self.info(f'source xml defined {en_xml}')
    
    def browse_translated_xml(self):
        out_xml = filedialog.askopenfilename(filetypes=[("XML files", "*.xml")])
        if out_xml and not out_xml.lower().endswith(".xml"):
            out_xml += ".xml"
        self.out_xml.set(out_xml)
        if out_xml:
            self.info(f'translated xml defined {out_xml}')

    def unpack_zip(self):
        zip_file = self.in_zip.get()
        if not zip_file:
            self.warn("please select the source ZIP file")
            messagebox.showerror("Error", "Please select the source ZIP file")
            return
        en_xml = self.en_xml.get()
        if not en_xml:
            self.warn("please select the source XML file")
            messagebox.showerror("Error", "Please select the source XML file")
            return
        map_file = self.map_file.get()
        if not map_file:
            self.warn("please select the mapping file")
            messagebox.showerror("Error", "Please select the mapping file")
            return
        
        self.unpacker = Unpacker(self.in_zip.get(),self.map_file.get(),self.en_xml.get())
        
        if self.unpacker.unpack():
            self.info("ZIP file unpacked successfully.")
        else:
            self.error("cannot unpack ZIP file")
            return 
        if self.unpacker.flatten():
            self.info("XML files flattened successfully.")
        else:
            self.error("cannot flatten XML file")
    
    def reconstruct_pack(self):
        out_xml = self.out_xml.get()
        if not out_xml:
            self.warn('please specify the translated XML file')
            messagebox.showerror("Error", "Please specify the translated XML file")
            return
        map_file = self.map_file.get()
        if not map_file:
            self.warn('please specify the mapping file')
            messagebox.showerror("Error", "Please specify the mapping file")
            return
        output_zip = self.out_zip.get()
        if not output_zip:
            self.warn('please specify the output ZIP file')
            messagebox.showerror("Error", "Please specify an output ZIP file")
            return
        
        self.packer = Packer(self.out_xml.get(), self.map_file.get(), self.out_zip.get())
        if self.packer.generate():
            self.info("Output folders generated successfully.")
        else:
            self.error("cannot generate output folders.")
            return 
        
        if self.packer.pack():
            self.info("ZIP file packed successfully.")
        else:
            self.error("cannot pack output ZIP file.")
    
    def run_all_steps(self):
        self.unpack_zip()
        self.info("Translation step (to be implemented)...")
        self.reconstruct_pack()
    
    def log(self, message):
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
    
    def info(self, message):
        self.log('[ INFO  ]: ' + message)
    
    def warn(self, message):
        self.log('[WARNING]: ' + message)

    def error(self, message):
        self.log('[ ERROR ]: ' + message)

if __name__ == "__main__":
    root = tk.Tk()
    app = XMLZipTranslatorApp(root)
    root.mainloop()
