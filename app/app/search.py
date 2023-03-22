from flask import current_app
from app import db
import shared.config as config
import shared.const as const
import logging
import json
from sqlalchemy import inspect
from shared.fulltext import getCols  
from models import Bestand, Artefact
import enum
from caching import cache


@cache.memoize()
def query_index(model, query, maxsize=1000, fields=['*']):
    if not current_app.elasticsearch:
        current_app.logger.error("Cannot search in elasticsearch since it is not instantiated....")
        return [], 0

    if hasattr(model, '__tablename__'):
        index = model.__tablename__.lower()
    else: 
        current_app.logger.error(f"Cannot search in elasticsearch: unknown tablename for {model}")
        return [], 0

    # Set basic query string
    query={'query_string': {'query': query, 'fields': fields, 'analyze_wildcard':True}}

    if issubclass(model, Artefact) and not model.__mapper_args__['polymorphic_identity'].value == 'Onbekend':
        value = model.__mapper_args__['polymorphic_identity'].value
        query = {'bool': {
            'filter': [{'multi_match': {'query': value, 'fields': ['artefactsoort']}}],
            'must': [query]}}
    if issubclass(model, Bestand) and not model.__mapper_args__['polymorphic_identity'] == const.BESTAND:
        value = model.__mapper_args__['polymorphic_identity']
        query = {'bool': {
            'filter': [{'multi_match': {'query': value, 'fields': ['bestandsoort']}}],
            'must': [query]}}

    current_app.logger.info(f'Quering Elastic index {index} with query {query}...')
    search = current_app.elasticsearch.search(
        index=index,
        query=query,
        size=maxsize,
        highlight={"fields": {"*": {}}, "pre_tags": "<mark>", "post_tags": "</mark>"},
        filter_path=['hits.hits._id', 'hits.hits._score', 'hits.hits.highlight','hits.total']
        )

    if search['hits']['total']['value'] == 0:
        search['hits']['hits'] = []

    hits = [{'primary_key': hit['_id'], const.FULLTEXT_SCORE_FIELD: hit['_score'], const.FULLTEXT_HIGHLIGHT_FIELD: hit['highlight']} for hit in search['hits']['hits']]
    hits = json.dumps(hits) 
    return hits, search['hits']['total']['value']


def add_to_index(model):
    if not current_app.elasticsearch:
        current_app.logger.error("Cannot search in elasticsearch since it is not instantiated....")
        return [], 0

    if hasattr(model, '__tablename__'):
        index = model.__tablename__.lower()
    else: 
        current_app.logger.error(f"Cannot search in elasticsearch: unknown tablename for {model}")
        return [], 0

    table = inspect(model).class_.__tablename__
    with db.engine.connect() as connection:            
        table_cols = getCols(connection, table)
        table_cols_keys = [col['name'].lower() for col in table_cols]
        
        model_fields = dir(model)
        model_fields = [field for field in model_fields if field.lower() in table_cols_keys] 

        payload = {}
        for field in model_fields:
            value = getattr(model, field)
            if value and issubclass(value.__class__, enum.Enum):
                value = value.value  
            payload[field.lower()] = value
    
        cache.delete_memoized(query_index)
        current_app.elasticsearch.update(index=index, id=model.primary_key, doc=payload, doc_as_upsert=True)


def remove_from_index(model):
    if not current_app.elasticsearch:
        current_app.logger.error("Cannot search in elasticsearch since it is not instantiated....")
        return [], 0

    if hasattr(model, '__tablename__'):
        index = model.__tablename__.lower()
    else: 
        current_app.logger.error(f"Cannot search in elasticsearch: unknown tablename for {model}")
        return [], 0

    cache.delete_memoized(query_index)
    current_app.elasticsearch.delete(index=index, id=model.primary_key)

