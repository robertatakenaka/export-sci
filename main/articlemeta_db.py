# coding: utf-8
import os
import logging
from datetime import datetime
from pymongo import MongoClient

from constants import WOS_ARTICLE_TYPES
from utils import earlier_datetime


class ArticleMetaDB(object):
    """Handle data from MongoDB."""

    def __init__(
        self,
        mongodb_host="localhost",
        mongodb_port=27017,
        mongodb_database="articlemeta",
        mongodb_collection="articles",
    ):
        db = MongoClient(mongodb_host)[mongodb_database]

        self._articles_coll = self._set_articles_coll(db)
        self._collections_coll = self._set_collections_coll(db)

    def _set_articles_coll(self, db):
        """Set articles collection."""
        coll = db["articles"]
        return coll

    def _set_collections_coll(self, db):
        """Set collections collection."""
        coll = db["collections"]
        return coll

    def load_pids_list_to_be_removed(self):
        """Load PIDs list to be removed."""
        now = datetime.now().isoformat()[0:10].replace("-", "")

        recorded_at = "controller/SCIELO_DEL_{0}.del".format(now)

        toremove = []

        with open(recorded_at, "wb") as f:
            for line in open("controller/takeoff.txt", "r"):
                sline = line.strip()
                toremove.append(sline)
                if len(sline) == 9:
                    for reg in self._articles_coll.find(
                        {"code_title": sline}, {"code": 1}
                    ):
                        f.write("SCIELO,{0},Y\r\n".format(reg["code"]))
                else:
                    f.write("SCIELO,{0},Y\r\n".format(sline))

            f.close()

        return toremove

    def sync_sent_documents(self, remove_origin=False):
        """Synchronize sent documents."""
        with open("controller/validated_ids.txt", "r") as f:
            for pid in f:
                self._articles_coll.update(
                    {"code": pid.strip()}, {"$set": {"sent_wos": "True"}}, multi=True
                )

        if remove_origin:
            os.remove("controller/validated_ids.txt")

    def mark_documents_as_sent_to_wos(self, pids):
        """Mark documents as sent to WoS."""
        for pid in pids:
            self._articles_coll.update(
                {"code": pid}, {"$set": {"sent_wos": "True"}}, multi=True
            )

    def load_collections_metadata(self):
        """Load collections metadata."""
        collections = self._collections_coll.find()

        dict_collections = {}
        for collection in collections:
            dict_collections.setdefault(collection["code"], collection)

        return dict_collections

    def set_elegible_document_types(self):
        """Set eligible document types efficiently using MongoDB query."""
        # Atualiza diretamente todos os documentos que atendem aos critérios
        self._articles_coll.update(
            {"applicable": "False", "article.v71.0._": {"$in": WOS_ARTICLE_TYPES}},
            {"$set": {"applicable": "True"}},
            multi=True,
        )

    def get_filter(
        self,
        wos_collections_allowed=None,
        code_title=None,
        publication_year=None,
        sent_wos=None,
        proc_date=None,
        updated_at=None,
        by_article_type=None,
    ):
        """Build filter dictionary for MongoDB queries.

        Args:
            wos_collections_allowed (list, optional): List of allowed WoS collections.
            code_title (str, optional): Code title to filter.
            publication_year (int, optional): Publication year filter.
            sent_wos (str, optional): Filter by sent_wos status ("True" or "False").
            proc_date (datetime, optional): Minimum processing date.
            by_article_type (bool, optional): Whether to filter by article type.

        Returns:
            dict: MongoDB filter criteria
        """
        fltr = {}

        # Adicionar filtros apenas se os parâmetros forem fornecidos
        if by_article_type:
            fltr["document_type"] = {"$in": WOS_ARTICLE_TYPES}

        # Adicionar filtros apenas se os parâmetros forem fornecidos
        if wos_collections_allowed:
            fltr["collection"] = {"$in": wos_collections_allowed}

        if code_title:
            fltr["code_title"] = code_title

        if publication_year:
            fltr["publication_year"] = str(publication_year)
        else:
            fltr["publication_year"] = {
                "$gte": str(1800)
            }  # valor padrão se não especificado

        if sent_wos is not None:
            fltr["sent_wos"] = sent_wos

        if proc_date:
            _proc_date = earlier_datetime(proc_date)
            fltr["processing_date"] = {"$gte": _proc_date}

        if updated_at:
            fltr["updated_at"] = {"$gte": updated_at}

        # Excluir documentos "ahead of print"
        fltr["$or"] = [
            {"article.v32": {"$exists": False}},
            {"article.v32.0._": {"$not": {"$regex": "ahead", "$options": "i"}}},
        ]
        return fltr

    def get_documents_by_filter(self, fltr, projection_fields=None):
        """Base method to get documents by filter criteria.

        Args:
            fltr (dict): MongoDB filter criteria
            projection_fields (dict, optional): Fields to include/exclude.

        Returns:
            pymongo.cursor.Cursor: Cursor of documents matching the filter
        """
        if projection_fields is None:
            projection_fields = {
                "code": 1,
                "collection": 1,
                "code_title": 1,
                "sent_wos": 1,
                "processing_date": 1,
                "publication_year": 1,
                "document_type": 1,
                "updated_at": 1,
                "created_at": 1,
            }

        logging.debug("Select documents: %s" % str(fltr))

        # Buscar os documentos completos diretamente em uma única consulta
        return self._articles_coll.find(fltr, projection_fields)

    def get_total_documents_by_filter(self, fltr):
        """Get total count of documents matching filter criteria.

        Args:
            fltr (dict): MongoDB filter criteria

        Returns:
            int: Total number of documents matching filter
        """
        # Total dos resultados
        return self._articles_coll.count_documents(fltr)

    def get_documents(self, fltr, projection_fields=None, skip=0, limit=None):
        """Get documents with pagination support.

        Args:
            fltr (dict): MongoDB filter criteria
            projection_fields (dict, optional): Fields to include/exclude
            skip (int): Number of documents to skip
            limit (int, optional): Maximum number of documents to return

        Returns:
            tuple: (total_count, cursor) with total count and document cursor
        """
        if projection_fields is None:
            projection_fields = {
                "code": 1,
                "collection": 1,
                "code_title": 1,
                "sent_wos": 1,
                "processing_date": 1,
                "publication_year": 1,
                "document_type": 1,
            }

        # Get total count first
        total = self.get_total_documents_by_filter(fltr)

        # Then get the documents with pagination
        cursor = self._articles_coll.find(fltr, projection_fields).order_by(
            "updated_at"
        )

        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        try:
            last_updated_at = cursor.first().updated_at
        except (TypeError, AttributeError):
            last_updated_at = datetime(1997, 1, 1)

        return total, cursor, last_updated_at

    def not_sent(
        self,
        wos_collections_allowed=None,
        code_title=None,
        publication_year=None,
        proc_date=None,
        by_article_type=None,
        projection_fields=None,
    ):
        """Get documents not sent to WoS."""
        # Construir o filtro
        fltr = self.get_filter(
            wos_collections_allowed=wos_collections_allowed,
            code_title=code_title,
            publication_year=publication_year,
            sent_wos="False",
            proc_date=proc_date,
            by_article_type=by_article_type,
        )

        # Obter documentos com o filtro
        return self.get_documents_by_filter(fltr, projection_fields)

    def sent_to_wos(
        self,
        wos_collections_allowed=None,
        code_title=None,
        publication_year=None,
        proc_date=None,
        by_article_type=None,
        projection_fields=None,
    ):
        """Get documents sent to WoS."""
        # Construir o filtro
        fltr = self.get_filter(
            wos_collections_allowed=wos_collections_allowed,
            code_title=code_title,
            publication_year=publication_year,
            sent_wos="True",
            proc_date=proc_date,
            by_article_type=by_article_type,
        )

        # Obter documentos com o filtro
        return self.get_documents_by_filter(fltr, projection_fields)

    def not_sent_with_proc_date(
        self,
        wos_collections_allowed=None,
        code_title=None,
        processing_date=None,
        publication_year=None,
        by_article_type=None,
        projection_fields=None,
    ):
        """Get documents not sent to WoS with processing date."""
        # Construir o filtro
        fltr = self.get_filter(
            wos_collections_allowed=wos_collections_allowed,
            code_title=code_title,
            publication_year=publication_year,
            sent_wos="False",
            proc_date=processing_date,
            by_article_type=by_article_type,
        )

        # Obter documentos com o filtro
        return self.get_documents_by_filter(fltr, projection_fields)

    def sent_to_wos_with_proc_date(
        self,
        wos_collections_allowed=None,
        code_title=None,
        processing_date=None,
        publication_year=None,
        by_article_type=None,
        projection_fields=None,
    ):
        """Get documents sent to WoS with processing date."""
        # Construir o filtro
        fltr = self.get_filter(
            wos_collections_allowed=wos_collections_allowed,
            code_title=code_title,
            publication_year=publication_year,
            sent_wos="True",
            proc_date=processing_date,
            by_article_type=by_article_type,
        )

        # Obter documentos com o filtro
        return self.get_documents_by_filter(fltr, projection_fields)

    def get_paginated_results(
        self, fltr, projection_fields=None, skip=0, limit=10, formatter=None
    ):
        """Get paginated results with total count and formatted results.

        Args:
            fltr (dict): MongoDB filter criteria
            projection_fields (dict, optional): Fields to include/exclude
            skip (int): Number of documents to skip
            limit (int): Maximum number of documents to return
            formatter (callable, optional): Function to format each document

        Returns:
            dict: Dictionary with pagination info and results
        """
        total, cursor = self.get_documents(
            fltr, projection_fields=projection_fields, skip=skip, limit=limit
        )

        # Calculate pagination info
        total_pages = (total + limit - 1) // limit if limit else 1
        current_page = (skip // limit) + 1 if limit else 1

        # Format results if formatter provided
        results = []
        for doc in cursor:
            if formatter:
                results.append(formatter(doc))
            else:
                results.append(doc)

        return {
            "total": total,
            "total_pages": total_pages,
            "current_page": current_page,
            "page_size": limit,
            "results": results,
        }
