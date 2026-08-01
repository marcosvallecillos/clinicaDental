import os
import json
import yaml
import logging
from typing import Dict, List, Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document  # ✅ ESTE CAMBIO
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning("⚠️ LangChain no instalado. RAG desactivado.")

logger = logging.getLogger(__name__)

class KnowledgeLoader:
    def __init__(self, pdfs_dir: str):
        self.pdfs_dir = pdfs_dir
        self.raw_text_knowledge = ""
        self.structured_json = {}
        self.rules_yaml = {}
        self.loaded_files = []
        self.vector_store = None
        self.embeddings = None

    def load_all_knowledge(self) -> Dict[str, Any]:
        """
        Carga todos los PDF, MD, JSON y YAML de la carpeta pdfs/
        + Crea un vector store FAISS para búsquedas semánticas
        """
        if not os.path.exists(self.pdfs_dir):
            logger.warning(f"⚠️ El directorio {self.pdfs_dir} no existe.")
            return {
                "text": "",
                "json": {},
                "yaml": {},
                "files": [],
                "vector_store": None,
                "has_rag": False
            }

        extracted_texts = []
        self.loaded_files = []

        # ===== PASO 1: Extraer texto de documentos =====
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
                        extracted_texts.append(pdf_text)
                        self.loaded_files.append(filename)
                        logger.info(f"✅ PDF cargado: {filename}")
                    except Exception as e:
                        logger.error(f"❌ Error leyendo PDF {filename}: {e}")
                else:
                    logger.warning(f"⚠️ pypdf no instalada. No se pudo leer {filename}")

            # Cargar Markdown (.md)
            elif filename.lower().endswith(".md"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        md_content = f.read()
                        extracted_texts.append(md_content)
                        self.loaded_files.append(filename)
                        logger.info(f"✅ Markdown cargado: {filename}")
                except Exception as e:
                    logger.error(f"❌ Error leyendo MD {filename}: {e}")

            # Cargar JSON
            elif filename.lower().endswith(".json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self.structured_json = json.load(f)
                        self.loaded_files.append(filename)
                        logger.info(f"✅ JSON cargado: {filename}")
                except Exception as e:
                    logger.error(f"❌ Error leyendo JSON {filename}: {e}")

            # Cargar YAML
            elif filename.lower().endswith(".yaml") or filename.lower().endswith(".yml"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self.rules_yaml = yaml.safe_load(f)
                        self.loaded_files.append(filename)
                        logger.info(f"✅ YAML cargado: {filename}")
                except Exception as e:
                    logger.error(f"❌ Error leyendo YAML {filename}: {e}")

        # Guardar texto completo
        self.raw_text_knowledge = "\n\n".join(extracted_texts)

        # ===== PASO 2: Crear Vector Store con RAG =====
        has_rag = False
        if LANGCHAIN_AVAILABLE and extracted_texts:
            try:
                logger.info("🔄 Inicializando embeddings de HuggingFace...")
                self.embeddings = HuggingFaceEmbeddings(
                    model_name="all-MiniLM-L6-v2",

                    cache_folder="./embeddings_cache"
                )
                
                logger.info("🔄 Dividiendo documentos en chunks...")
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=500,
                    chunk_overlap=50
                )
                
                # ✅ IMPORTANTE: Crear documentos de LangChain
                all_chunks = []
                for text in extracted_texts:
                    chunks = splitter.split_text(text)
                    all_chunks.extend(chunks)
                
                logger.info(f"✅ Creados {len(all_chunks)} chunks de texto")
                
                # ✅ CONVERTIR A DOCUMENTOS DE LANGCHAIN
                documents = [Document(page_content=chunk) for chunk in all_chunks]
                
                logger.info("🔄 Creando vector store FAISS...")
                self.vector_store = FAISS.from_documents(documents, self.embeddings)
                logger.info("✅ Vector store FAISS creado correctamente")
                has_rag = True
                
            except Exception as e:
                logger.error(f"❌ Error creando RAG: {e}")
                self.vector_store = None
                has_rag = False
        else:
            if not LANGCHAIN_AVAILABLE:
                logger.info("⚠️ LangChain no instalado. RAG desactivado.")
            elif not extracted_texts:
                logger.info("⚠️ No hay documentos cargados. RAG desactivado.")

        return {
            "text": self.raw_text_knowledge,
            "json": self.structured_json,
            "yaml": self.rules_yaml,
            "files": self.loaded_files,
            "vector_store": self.vector_store,
            "embeddings": self.embeddings,
            "has_rag": has_rag
        }

    def search_knowledge(self, query: str, k: int = 3) -> List[str]:
        """Busca documentos relevantes usando RAG"""
        if not self.vector_store:
            logger.warning("⚠️ Vector store no disponible. RAG desactivado.")
            return []
        
        try:
            docs = self.vector_store.similarity_search(query, k=k)
            results = [doc.page_content for doc in docs]
            logger.info(f"✅ RAG encontró {len(results)} documentos relevantes")
            return results
        except Exception as e:
            logger.error(f"❌ Error en búsqueda RAG: {e}")
            return []

    def get_context_for_query(self, query: str) -> str:
        """Obtiene contexto relevante para una consulta"""
        relevant_docs = self.search_knowledge(query, k=3)
        if relevant_docs:
            context = "\n---\n".join(relevant_docs)
            return f"CONTEXTO RELEVANTE DEL MANUAL:\n{context}"
        return ""

    def get_summary(self) -> Dict[str, Any]:
        """Resumen de lo cargado"""
        return {
            "files_count": len(self.loaded_files),
            "files": self.loaded_files,
            "has_pdf": any(f.endswith('.pdf') for f in self.loaded_files),
            "has_md": any(f.endswith('.md') for f in self.loaded_files),
            "has_json": any(f.endswith('.json') for f in self.loaded_files),
            "has_yaml": any(f.endswith('.yaml') for f in self.loaded_files),
            "rag_enabled": self.vector_store is not None,
            "text_size": len(self.raw_text_knowledge)
        }