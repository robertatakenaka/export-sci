#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Módulo para processamento de documentos científicos para o Web of Science (WoS).
Implementa funcionalidades para coletar, processar e enviar documentos.
"""

import os
import sys
import logging
from datetime import datetime
import json
from typing import Dict, List, Optional, Tuple, Any, Union, cast


# Importações específicas do projeto
from constants import WOS_COLLECTIONS_ALLOWED, WOS_ARTICLE_TYPES
from articlemeta_db import ArticleMetaDB
from local_db import WosDocument, CollectionStats


# Configuração do logger
logger = logging.getLogger(__name__)

# Configuração do MongoDB
# MONGODB_HOST = os.environ.get("MONGODB_HOST", "localhost")


class LocalDBCreator:
    """
    Classe para processar documentos de uma coleção e ISSN específicos.
    Cada instância é dedicada a uma única combinação de coleção e código de título.
    """

    # Dicionário para armazenar instâncias já criadas
    _instances = {}

    @classmethod
    def get_instance(cls, collection, code_title, am_mongodb_host):
        """
        Obtém uma instância existente ou cria uma nova.

        Args:
            collection (str): Código da coleção a ser processada
            code_title (str): Código do título/ISSN
            am_mongodb_host (str): Host do MongoDB

        Returns:
            Harvester: Uma instância do Harvester para o par collection/code_title
        """
        instance_key = f"{collection}_{code_title}"
        if instance_key not in cls._instances:
            cls._instances[instance_key] = cls(collection, code_title, am_mongodb_host)
        return cls._instances[instance_key]

    def __init__(self, collection, code_title, am_mongodb_host):
        """
        Inicializa o processador para uma coleção e ISSN específicos.

        Args:
            collection (str): Código da coleção a ser processada
            code_title (str): Código do título/ISSN
            am_mongodb_host (str): Host do MongoDB
        """
        logger.debug(
            f"Inicializando Harvester para coleção {collection}, código {code_title} (MongoDB: {am_mongodb_host})"
        )
        self.collection = collection
        self.code_title = code_title
        self.amdb = ArticleMetaDB(am_mongodb_host)

    def check_documents_exist(self):
        """Verifica se existem documentos para o ISSN na coleção."""
        fltr = self.amdb.get_filter(
            wos_collections_allowed=[self.collection],
            code_title=self.code_title,
        )
        return self.amdb.get_total_documents_by_filter(fltr)

    def get_documents(self, publication_year):
        """
        Processa documentos de um ano específico.

        Args:
            publication_year (int): Ano de publicação

        Returns:
            tuple: (total, total_docs) com totais de documentos
        """
        # Criar filtro para obter total de documentos

        next_harvest_date = datetime(1997, 1, 1)
        collection_stats_total = 0
        collection_stats = CollectionStats.get(
            self.collection, self.code_title, publication_year
        )
        if collection_stats:
            next_harvest_date = datetime.fromstring(collection_stats.next_harvest_date)
            collection_stats_total = collection_stats.total

        fltr = self.amdb.get_filter(
            wos_collections_allowed=[self.collection],
            code_title=self.code_title,
            publication_year=publication_year,
        )
        total = self.amdb.get_total_documents_by_filter(fltr)
        if collection_stats_total == total:
            # não há novos registros
            return total, 0

        fltr = self.amdb.get_filter(
            wos_collections_allowed=[self.collection],
            code_title=self.code_title,
            publication_year=publication_year,
            updated_at__gte=next_harvest_date,
        )
        # Obter documentos
        total_docs, docs = self.amdb.get_documents(fltr)

        # Log do total
        logger.info(
            f"{self.collection}/{self.code_title}/{publication_year}: {total_docs}/{total} documentos"
        )

        # Processar cada documento
        success_count = 0
        error_count = 0

        doc = None

        for index, doc in enumerate(docs, 1):
            success, message = WosDocument.create_or_update(doc)
            if success:
                success_count += 1
                logger.debug(
                    f"{self.collection}/{self.code_title}/{doc['code']}: {index}/{total_docs} - {message}"
                )
            else:
                error_count += 1
                logger.error(
                    f"{self.collection}/{self.code_title}/{doc['code']}: {message}"
                )

        # Salvar estatísticas
        if doc:
            next_harvest_date = doc.updated_at
        self._save_stats(
            collection_stats, publication_year, total, total_docs, next_harvest_date
        )

        return total, total_docs

    def _save_stats(self, publication_year, total, filtered_total, next_harvest_date):
        """Salva estatísticas no banco de dados."""
        collection_stat = CollectionStats.create(
            dict(
                collection=self.collection,
                code_title=self.code_title,
                total_documents=total,
                filtered_documents=filtered_total,
                publication_year=publication_year,
                next_harvest_date=next_harvest_date,
            )
        )

    def close(self):
        """Fecha conexões e libera recursos."""
        # Remover a instância da lista de instâncias
        instance_key = f"{self.collection}_{self.code_title}"
        if instance_key in self.__class__._instances:
            del self.__class__._instances[instance_key]

    def __enter__(self):
        """Suporte para o uso com with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Fecha conexões ao sair do contexto."""
        self.close()


def harvest(issns):
    """
    Função para processar documentos de múltiplas coleções.

    Args:
        issns (list or dict): Lista geral de ISSNs

    Returns:
        dict: Dicionário atualizado de ISSNs por coleção
    """
    start_year = 2002
    end_year = datetime.now().year + 2
    for collection, issns in issn_by_collection.items():
        # Processar ISSNs para esta coleção
        for code_title in issns:
            with Harvester.get_instance(collection, code_title) as harvester:
                # Processar cada ano
                for year in range(start_year, end_year):
                    harvester.get_documents(str(year))


if __name__ == "__main__":
    # Configuração do logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Exemplo de uso
    sample_issns = ["1234-5678", "8765-4321"]
    result = harvest(sample_issns)
    print(f"Resultado: {result}")
