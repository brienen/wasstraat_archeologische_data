from flask import current_app
import shared.config as config
import shared.const as const
import logging
import json

logger = logging.getLogger()



def add_to_index(index, model):
    if not current_app.elasticsearch:
        return
    payload = {}
    for field in model.__searchable__:
        payload[field] = getattr(model, field)
    current_app.elasticsearch.index(index=index, id=model.id, body=payload)


def remove_from_index(index, model):
    if not current_app.elasticsearch:
        return
    current_app.elasticsearch.delete(index=index, id=model.id)


def query_index(model, query, maxsize=1000, fields=['*']):
    if not current_app.elasticsearch:
        logger.error("Cannot search in elasticsearch since it is not instantiated....")
        return [], 0

    if hasattr(model, '__tablename__'):
        index = model.__tablename__.lower()
    else: 
        logger.error(f"Cannot search in elasticsearch: unknown tablename for {model}")
        return [], 0

    fields = ['*' + field.lower() for field in fields] if fields != ['*'] else ['*']
    search = current_app.elasticsearch.search(
        index=index,
        body={'query': {'simple_query_string': {'query': query, 'analyze_wildcard':True, 'fields': fields}}, 
              'size': maxsize})
    hits = [{'primary_key': hit['_id'], 'score': hit['_score']} for hit in search['hits']['hits']]
    hits = json.dumps(hits) 
    return hits, search['hits']['total']['value']