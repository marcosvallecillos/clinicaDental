import os
import json
import yaml
from typing import Dict, List, Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

class KnowledgeLoader:
    def __init__(self, pdfs_dir: str):
        self.pdfs_dir = pdfs_dir
        self.raw_text_knowledge = ""
        self.structured_json = {}
        self.rules_yaml = {}
        self.loaded_files = []

    def load_all_knowledge(self) -> Dict[str, Any]:
        """Carga todos los PDF, MD, JSON y YAML de la carpeta pdfs/"""
        if not os.path.exists(self.pdfs_dir):
            print(f"⚠️ El directorio {self.pdfs_dir} no existe.")
            return {"text": "", "json": {}, "yaml": {}, "files": []}

        extracted_texts = []
        self.loaded_files = []

        for filename in os.listdir(self.pdfs_dir):
            file_path = os.path.join(self.pdfs_dir, filename)
            
            # Cargar PDF
            if filename.lower().endswith(".pdf"):
                if PdfReader:
                    try:
                        reader = PdfReader(file_path)
                        pdf_text = ""
                        for page in reader.pages:
                            text = page.extract_text()
                            if text:
                                pdf_text += text + "\n"
                        extracted_texts.append(f"--- DOCUMENTO PDF: {filename} ---\n{pdf_text}")
                        self.loaded_files.append(filename)
                    except Exception as e:
                        print(f"Error leyendo PDF {filename}: {e}")
                else:
                    print(f"⚠️ Librería pypdf no instalada. No se pudo leer {filename}")

            # Cargar Markdown (.md)
            elif filename.lower().endswith(".md"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        md_content = f.read()
                        extracted_texts.append(f"--- MANUAL MARKDOWN: {filename} ---\n{md_content}")
                        self.loaded_files.append(filename)
                except Exception as e:
                    print(f"Error leyendo MD {filename}: {e}")

            # Cargar JSON
            elif filename.lower().endswith(".json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self.structured_json = json.load(f)
                        self.loaded_files.append(filename)
                except Exception as e:
                    print(f"Error leyendo JSON {filename}: {e}")

            # Cargar YAML
            elif filename.lower().endswith(".yaml") or filename.lower().endswith(".yml"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self.rules_yaml = yaml.safe_load(f)
                        self.loaded_files.append(filename)
                except Exception as e:
                    print(f"Error leyendo YAML {filename}: {e}")

        self.raw_text_knowledge = "\n\n".join(extracted_texts)
        return {
            "text": self.raw_text_knowledge,
            "json": self.structured_json,
            "yaml": self.rules_yaml,
            "files": self.loaded_files
        }

    def get_summary(self) -> Dict[str, Any]:
        return {
            "files_count": len(self.loaded_files),
            "files": self.loaded_files,
            "has_pdf": any(f.endswith('.pdf') for f in self.loaded_files),
            "has_md": any(f.endswith('.md') for f in self.loaded_files),
            "has_json": any(f.endswith('.json') for f in self.loaded_files),
            "has_yaml": any(f.endswith('.yaml') for f in self.loaded_files)
        }
