import json
from jsonschema import validate, ValidationError
from flask import Response, request, url_for
from flask_restful import Resource
from sqlalchemy.exc import IntegrityError
from imagenet_browser import db
from imagenet_browser.models import Synset, Image
from imagenet_browser.constants import *
from imagenet_browser.utils import ImagenetBrowserBuilder, create_error_response

#TODO The GET methods of SynsetCollection and SynsetHyponymCollection should paginate their items

class SynsetCollection(Resource):

    def get(self):
        body = ImagenetBrowserBuilder()
        
        body.add_namespace("imagenet_browser", LINK_RELATIONS_URL)
        body.add_control("self", url_for("api.synsetcollection"))
        body.add_control_add_synset()
        body["items"] = []
        for synset in Synset.query.all():
            item = ImagenetBrowserBuilder(
                wnid=synset.wnid,
                words=synset.words,
                gloss=synset.gloss
            )
            item.add_control("self", url_for("api.synsetitem", wnid=synset.wnid))
            item.add_control("profile", SYNSET_PROFILE)
            body["items"].append(item)
            
        return Response(json.dumps(body), 200, mimetype=MASON)

    def post(self):
        if not request.json:
            return create_error_response(
                415,
                "Unsupported media type",
                "Requests must be JSON"
            )

        try:
            validate(request.json, Synset.get_schema())
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))

        synset = Synset(
            wnid=request.json["wnid"],
            words=request.json["words"],
            gloss=request.json["gloss"]
        )

        try:
            db.session.add(synset)
            db.session.commit()
        except IntegrityError:
            return create_error_response(
                409,
                "Already exists",
                "Synset with WordNet ID of '{}' already exists.".format(request.json["wnid"])
            )

        return Response(status=201, headers={
            "Location": url_for("api.synsetitem", wnid=request.json["wnid"])
        })

class SynsetItem(Resource):

    def get(self, wnid):
        synset = Synset.query.filter_by(wnid=wnid).first()
        if not synset:
            return create_error_response(
                404,
                "Not found",
                "No synset with WordNet ID of '{}' found".format(wnid)
            )

        body = ImagenetBrowserBuilder(
            wnid=wnid,
            words=synset.words,
            gloss=synset.gloss
        )
        body.add_namespace("imagenet_browser", LINK_RELATIONS_URL)
        body.add_control("self", url_for("api.synsetitem", wnid=wnid))
        body.add_control("profile", SYNSET_PROFILE)
        body.add_control("collection", url_for("api.synsetcollection"))
        body.add_control_edit_synset(wnid=wnid)
        body.add_control_delete_synset(wnid=wnid)
        body.add_control("imagenet_browser:synsetimagecollection", url_for("api.synsetimagecollection", wnid=wnid))
        body.add_control("imagenet_browser:synsethyponymcollection", url_for("api.synsethyponymcollection", wnid=wnid))

        return Response(json.dumps(body), 200, mimetype=MASON)

    def put(self, wnid):
        synset = Synset.query.filter_by(wnid=wnid).first()
        if not synset:
            return create_error_response(
                404,
                "Not found",
                "No synset with WordNet ID of '{}' found".format(wnid)
            )

        if not request.json:
            return create_error_response(
                415,
                "Unsupported media type",
                "Requests must be JSON"
            )

        try:
            validate(request.json, Synset.get_schema())
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))

        synset.wnid = request.json["wnid"]
        synset.words = request.json["words"]
        synset.gloss = request.json["gloss"]

        try:
            db.session.commit()
        except IntegrityError:
            return create_error_response(
                409,
                "Already exists", 
                "Synset with WordNet ID of '{}' already exists.".format(synset.wnid)
            )

        return Response(status=204)

    def delete(self, wnid):
        synset = Synset.query.filter_by(wnid=wnid).first()
        if not synset:
            return create_error_response(
                404,
                "Not found",
                "No synset with WordNet ID of '{}' found".format(wnid)
            )

        db.session.delete(synset)
        db.session.commit()

        return Response(status=204)


class SynsetHyponymCollection(Resource):

    def get(self, wnid):
        synset = Synset.query.filter_by(wnid=wnid).first()
        if not synset:
            return create_error_response(
                404,
                "Not found",
                "No synset with WordNet ID of '{}' found".format(wnid)
            )

        body = ImagenetBrowserBuilder(
            wnid=wnid,
            words=synset.words,
            gloss=synset.gloss
        )
        body.add_namespace("imagenet_browser", LINK_RELATIONS_URL)
        body.add_control("self", url_for("api.synsethyponymcollection", wnid=wnid))
        body["items"] = []
        for synset_hyponym in synset.hyponyms:
            item = ImagenetBrowserBuilder(
                wnid=synset_hyponym.wnid,
                words=synset_hyponym.words,
                gloss=synset_hyponym.gloss
            )
            item.add_control("self", url_for("api.synsetitem", wnid=synset_hyponym.wnid))
            item.add_control("profile", SYNSET_PROFILE)
            body["items"].append(item)

        return Response(json.dumps(body), 200, mimetype=MASON)