'''
    translator for FBReader strings on: https://fbreader.org/translations
    Daniel Zhang 
    2025
    update log: 

    v 0.0.2: download en.zip from: https://fbreader.org/static/strings/android/en.zip
    v 0.0.1: initial implementation
    - unpacker and packer, tested working
'''

import zipfile
import traceback
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def download_zip(url: str, save_path: str) -> bool:
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Downloaded ZIP file to {save_path}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to download ZIP file: {e}")
        return False
    
class Unpacker:
    def __init__(self, in_zip : Optional[str] = None, map_file : Optional[str] = None, out_xml : Optional[str] = None) -> None:
        self.in_zip = Path(in_zip) if in_zip else None
        self.map_file = Path(map_file) if map_file else None
        self.out_xml = Path(out_xml) if out_xml else None
        # get the file name only, .name will return the file name with ext
        self.out_dir = Path(Path(self.in_zip).stem)
        # string::name -> relative path
        self.entries = {}

    def unpack(self) -> bool:
        ''' unpack zip file to out_dir '''
        if not self.in_zip or not self.in_zip.exists():
            logger.error("ZIP file not found.")
            return False
        
        try:
            with zipfile.ZipFile(self.in_zip, 'r') as zip_ref:
                zip_ref.extractall(self.out_dir)
            
            logger.info(f'Zip file [{self.in_zip}] unpacked to: {self.out_dir}')
            return True
        except:
            traceback.print_exc()
            return False
    
    def indent(self, elem, level=0):
        ''' add indention to xml elements '''
        i = "\n" + level * "    "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for subelem in elem:
                self.indent(subelem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        elif level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

    def flatten(self) -> bool:
        ''' flatten all xml contents into a single xml file, generate mapping file at the same time '''
        if not self.out_dir.exists():
            logger.error("Extracted directory not found.")
            return False
        
        try:
            root = ET.Element("resources")
            # cycle xmls
            for xml_file in self.out_dir.rglob("*.xml"):
                rel_path = xml_file.relative_to(self.out_dir)
                tree = ET.parse(xml_file)
                # cycle string entries
                for string in tree.findall(".//string"):
                    name = string.get("name")
                    if name:
                        if name not in self.entries:
                            self.entries[name] = []
                        self.entries[name].append(str(rel_path))
                        elem = ET.SubElement(root, "string", name=name)
                        elem.text = string.text
            logger.info('XML files data collected')

            # write out xml
            self.indent(root)
            tree = ET.ElementTree(root)
            tree.write(self.out_xml, encoding="utf-8", xml_declaration=True)
            logger.info(f'XML files flattened: {self.out_xml}')

            # write map file
            if self.map_file:
                with self.map_file.open("w", encoding="utf-8") as f:
                    for key, values in self.entries.items():
                        for value in values:
                            f.write(f"{key}::{value}\n")
            logger.info(f'Mapping file generated: {self.map_file}')
            
            return True
        except:
            traceback.print_exc()
            return False

    def info(self) -> str:
        ''' display all information '''
        msg = f'{self.in_zip=}, {self.out_dir=}, {self.map_file=}, {self.out_xml=}'
        logger.info(msg)
        return msg
    

class Packer:
    def __init__(self, in_xml: Optional[str] = None, map_file: Optional[str] = None, out_zip: Optional[str] = None) -> None:
        self.in_xml = Path(in_xml) if in_xml else None
        self.map_file = Path(map_file) if map_file else None
        self.out_zip = Path(out_zip) if out_zip else None
        # extract the file name only
        self.lang_suffix = Path(self.in_xml).stem
        self.out_dir = Path(self.lang_suffix)
        self.entries = {}
        
    def load_map(self) -> bool:
        ''' load mapping files for folder structure '''
        try:
            if not self.map_file or not self.map_file.exists():
                print("Map file not found.")
                return False
            
            with self.map_file.open("r", encoding="utf-8") as f:
                for line in f:
                    key, value = line.strip().split("::")
                    if key not in self.entries:
                        self.entries[key] = []
                    self.entries[key].append(Path(value))
            
            logger.info(f'Mapping file loaded: {self.map_file}')
            return True
        except:
            traceback.print_exc()
            return False

    def modify_folder_name(self, path: Path) -> Path:
        ''' modify the last level folder name from values to values-lang '''
        parts = list(path.parts)
        if parts[-2].startswith("values"):
            parts[-2] = parts[-2] + '-' + self.lang_suffix
        return Path(*parts)

    def generate(self) -> bool:
        ''' generate proper folder structure '''
        if not self.load_map():
            return False
        
        try:
            tree = ET.parse(self.in_xml)
            root = tree.getroot()
            
            for key, rel_paths in self.entries.items():
                for rel_path in rel_paths:
                    modified_path = self.modify_folder_name(rel_path)
                    xml_path = self.out_dir / modified_path
                    xml_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    if xml_path.exists():
                        tree = ET.parse(xml_path)
                        xml_root = tree.getroot()
                    else:
                        xml_root = ET.Element("resources")
                    
                    elem = xml_root.find(f".//string[@name='{key}']")
                    if not elem:
                        elem = ET.SubElement(xml_root, "string", name=key)
                    
                    elem.text = root.find(f".//string[@name='{key}']").text
                    
                    new_tree = ET.ElementTree(xml_root)
                    new_tree.write(xml_path, encoding="utf-8", xml_declaration=True)
            logger.info(f'Folder structure generated: {self.out_dir}')
            return True
        except:
            traceback.print_exc()
            return False

    def pack(self) -> bool:
        ''' pack the folder to a zip file '''
        if not self.out_dir.exists():
            print("Translated directory not found.")
            return False
        
        try:
            with zipfile.ZipFile(self.out_zip, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for file in self.out_dir.rglob("*"):
                    zip_ref.write(file, file.relative_to(self.out_dir))
            
            logger.info(f'Zip file generated: {self.out_zip}')
            return True
        except:
            traceback.print_exc()
            return False

    def info(self) -> str:
        ''' display all information '''
        msg = f'{self.in_xml=}, {self.out_zip=}, {self.out_dir=}, {self.map_file=}'
        logger.info(msg)
        return msg

if __name__=='__main__':
    en_url = r'https://fbreader.org/static/strings/android/en.zip'
    src_lang = 'en'
    des_lang = 'zh-rTW'
    in_zip = f'{src_lang}.zip'
    out_zip = f'{des_lang}.zip'
    map_file = 'mapping'
    en_xml = f'{src_lang}.xml'
    zh_xml = f'{des_lang}.xml'
    temp_dir = des_lang

    if download_zip(en_url, in_zip):
        # unpack
        if Path(in_zip).exists() and not Path(map_file).exists() and not Path(zh_xml).exists():
            up = Unpacker(in_zip,map_file,en_xml)
            if up.unpack():
                if up.flatten():
                    up.info()
                else:
                    logger.error('Flatten error')
            else:
                logger.error('Unpack error')
        else:
            logger.info(f'{in_zip} has been flattened: {en_xml}')
            logger.info(f'mapping file has been generated: {map_file}')
        # pack
        if Path(zh_xml).exists() and Path(map_file).exists() and not Path(out_zip).exists():
            pc = Packer(zh_xml, map_file, out_zip)
            if pc.generate():
                if pc.pack():
                    pc.info()
                else:
                    logger.error('Pack error')
            else:
                logger.error('Generate folder error')
        else:
            logger.info(f'Output file has been generated: {out_zip}')
    else:
        logger.error(f'Cannot download en.zip from: {en_url})
