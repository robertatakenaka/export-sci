"""
Módulo enxuto para processamento de documentos WoS com MongoEngine

Este módulo implementa classes para gerenciar documentos da Web of Science (WoS)
usando MongoDB como backend de armazenamento através da biblioteca MongoEngine.

Principais componentes:
- WosDocument: Representa um documento WoS com seus metadados e estado de processamento
- CollectionStats: Armazena estatísticas sobre coleções de documentos

Campos importantes do WosDocument:
- created_at/updated_at: Datas de criação/atualização do registro no ArticleMeta (AM)
- xml_date: Data em que o XML foi gerado para envio ao WoS
- reproc: Flag que indica se o documento precisa ser reprocessado
"""

from mongoengine import (
    connect,
    Document,
    StringField,
    BooleanField,
    DateTimeField,
    DictField,
    ListField,
    IntField,
    Q,
)
from datetime import datetime


# Constantes para tipos de artigos aceitos pelo WoS
class constants:
    # Lista de tipos de documentos aceitos pelo WoS
    WOS_ARTICLE_TYPES = [
        "article",
        "review",
        "letter",
        "editorial",
        "proceeding",
        "book",
        "book_chapter",
    ]


# Conexão
connect("wos_database", host="mongodb://localhost:27017/")


def get_default_datetime():
    return datetime(1997, 1, 1)


class BaseDocument(Document):
    created = DateTimeField(default=datetime.utcnow)
    updated = DateTimeField(default=datetime.utcnow)

    meta = {"abstract": True}

    def save(self, *args, **kwargs):
        self.updated = datetime.utcnow()
        return super().save(*args, **kwargs)


class WosDocument(BaseDocument):
    code = StringField(required=True)
    collection = StringField(required=True)
    code_title = StringField(required=True)
    publication_year = StringField()
    document_type = StringField()
    sent_wos = BooleanField(default=False)
    processing_date = StringField()
    created_at = DateTimeField()  # Data de criação do registro no ArticleMeta (AM)
    updated_at = DateTimeField()  # Data de atualização do registro no ArticleMeta (AM)
    xml_date = (
        DateTimeField()
    )  # Alterado de xml_generated (str) para xml_date (datetime)
    harvest_date = DateTimeField()  # Novo campo adicionado
    reproc = BooleanField(default=False)  # Nova flag adicionada
    errors = ListField(DictField())
    has_error = BooleanField(default=False)

    meta = {
        "collection": "wos_processing",
        "indexes": [
            "collection",
            "publication_year",
            "code_title",
            "sent_wos",
            "updated_at",
            "xml_date",
            "has_error",
            "reproc",
        ],
        # Definição de unique como a tupla (collection, code_title, code)
        "unique_together": [("collection", "code_title", "code")],
    }

    @classmethod
    def get(cls, code):
        return cls.objects.get(code=code)

    @classmethod
    def create_or_update(cls, data):
        code = data.get("code")
        if not code:
            return False, "Campo 'code' obrigatório"

        # Processar errors se for string
        try:
            if isinstance(data.get("errors"), str):
                data["errors"] = [{"message": data["errors"]}]
                data["has_error"] = True
            elif data.get("errors") is None:
                data["errors"] = []
                data["has_error"] = False
        except:
            data["errors"] = []
            data["has_error"] = False

        try:
            doc = cls.get(code)

            # Verificar se updated_at é posterior a xml_date
            if "updated_at" in data and doc.xml_date:
                if data["updated_at"] > doc.xml_date:
                    data["reproc"] = True

            # Atualizar campos existentes
            for key, value in data.items():
                if key != "code":  # Não modificar a chave primária
                    setattr(doc, key, value)
            doc.save()
            return True, doc

        except cls.DoesNotExist:
            return cls.create(data)

    @classmethod
    def create(cls, data):
        # Criar novo documento
        doc = cls(**data)
        doc.save()
        return True, doc

    @classmethod
    def get_items(
        cls, collection=None, code_title=None, publication_year=None, extra_params=None
    ):
        query = {}
        # Adicionar filtros opcionais se fornecidos
        if collection:
            query["collection"] = collection
        if code_title:
            query["code_title"] = code_title
        if publication_year:
            query["publication_year"] = publication_year

        # Adicionar filtro fixo de document_type
        query["document_type__in"] = constants.WOS_ARTICLE_TYPES

        # Adicionar parâmetros extras
        if extra_params:
            query.update(extra_params)

        return cls.objects(**query)

    @classmethod
    def get_pending(cls, collection=None, code_title=None, publication_year=None):
        extra_params = dict(sent_wos__ne=True, xml_date__isnull=True)
        return cls.get_items(collection, code_title, publication_year, extra_params)

    @classmethod
    def get_sent_to_wos(
        cls, collection=None, code_title=None, publication_year=None, sent_wos=True
    ):
        if sent_wos:
            extra_params = dict(sent_wos=sent_wos)
        else:
            extra_params = {"sent_wos__ne": True}
        return cls.get_items(collection, code_title, publication_year, extra_params)

    @classmethod
    def get_with_errors(cls, collection=None, code_title=None, publication_year=None):
        """
        Retorna documentos (collection, issn, publication_year) que possuem erros
        """
        extra_params = {"has_error": True}
        return cls.get_items(collection, code_title, publication_year, extra_params)

    @classmethod
    def get_reproc(cls, collection=None, code_title=None, publication_year=None):
        """
        Retorna documentos (collection, issn, publication_year) que possuem erros
        """
        extra_params = {"reproc": True}
        return cls.get_items(collection, code_title, publication_year, extra_params)


class CollectionStats(BaseDocument):
    collection = StringField(required=True)
    code_title = StringField(required=True)
    total_documents = IntField(required=True)
    filtered_documents = IntField(required=True)
    publication_year = StringField(required=True)
    next_harvest_date = DateTimeField(default=get_default_datetime)

    meta = {
        "collection": "collection_stats",
        "indexes": [
            "collection",
            "publication_year",
            "code_title",
            "next_harvest_date",
        ],
    }

    @classmethod
    def get(cls, collection, code_title, publication_year):
        try:
            return (
                cls.objects(
                    collection=collection,
                    code_title=code_title,
                    publication_year=publication_year,
                )
                .order_by("-next_harvest_date")
                .first()
            )
        except Exception:
            return None

    @classmethod
    def create(cls, data):
        try:
            stats = cls(**data).save()
            return True, stats
        except Exception as e:
            return False, str(e)


# Exemplo de uso
if __name__ == "__main__":
    # Criar documentos
    success, doc1 = WosDocument.create_or_update(
        {
            "code": "ABC12345",
            "collection": "SCI",
            "code_title": "1234-5678",
            "publication_year": "2022",
            "document_type": "article",
            "errors": "Erro de validação",
            "created_at": datetime(2022, 5, 15),
            "updated_at": datetime(2022, 5, 15),
        }
    )

    success, doc2 = WosDocument.create_or_update(
        {
            "code": "DEF67890",
            "collection": "MED",
            "code_title": "2345-6789",
            "publication_year": "2023",
            "document_type": "review",
            "xml_date": datetime(2023, 1, 20),
            "created_at": datetime(2023, 1, 15),
            "updated_at": datetime(2023, 1, 15),
        }
    )

    # Criar estatística
    success, stats1 = CollectionStats.create(
        {
            "collection": "SCI",
            "code_title": "1234-5678",
            "total_documents": 10,
            "filtered_documents": 8,
            "publication_year": "2022",
        }
    )

    # Buscar documento específico
    doc = WosDocument.get("ABC12345")
    if doc:
        print(f"Documento encontrado: {doc.code}, tipo: {doc.document_type}")

    # Buscar estatística específica
    stats = CollectionStats.get("SCI", "1234-5678", "2022")
    if stats:
        print(
            f"Estatística encontrada: {stats.collection}, docs: {stats.filtered_documents}/{stats.total_documents}"
        )

    # Consultas de documentos pendentes
    print("\nDocumentos pendentes:")
    for doc in WosDocument.get_pending():
        print(f"  - {doc.collection}: {doc.code_title} ({doc.publication_year})")

    # Consultas de documentos com erros
    print("\nDocumentos com erros:")
    for doc in WosDocument.get_with_errors():
        print(f"  - {doc.collection}: {doc.code_title} ({doc.publication_year})")

    # Documentos por ano
    print("\nDocumentos por ano:")
    for doc in WosDocument.objects(
        publication_year="2023", document_type__in=constants.WOS_ARTICLE_TYPES
    ):
        print(f"  - {doc.code}: {doc.document_type}")

    # Atualizar documento existente
    success, doc_updated = WosDocument.create_or_update(
        {
            "code": "ABC12345",
            "document_type": "review",  # Alterando o tipo
            "has_error": False,  # Resolvendo o erro
            "updated_at": datetime(
                2023, 2, 15, 10, 20, 30
            ),  # Data posterior à xml_date
            # Isso deve ativar o flag reproc automaticamente se xml_date existir
        }
    )
