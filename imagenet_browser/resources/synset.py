import json
from jsonschema import validate, ValidationError
from flask import Response, request, url_for
from flask_restful import Resource
from sqlalchemy.exc import IntegrityError
from imagenet_browser import db
from imagenet_browser.models import Synset, Image
from imagenet_browser.constants import *
from imagenet_browser.utils import ImagenetBrowserBuilder, create_error_response

class SynsetCollection(Resource):
    """
    Subclass of Resource that defines the HTTP method handlers for the SynsetCollection resource.
    Error scenarios for the various methods are described in the calls to create_error_response, or alternatively, in the resource tests.
    All synsets known to the API.
    """

    def get(self):
        """
        Build and return a list of all synsets known to the API.
        A list has SYNSET_PAGE_SIZE items with the starting index being controlled by the query parameter.
        As such, the next and prev controls become available when appropriate.
        """
        try:
            start = int(request.args.get("start", default=0))
        except ValueError:
            return create_error_response(
                400,
                "Invalid query parameter",
                "Query parameter 'start' must be an integer"
            )

        body = ImagenetBrowserBuilder()
        
        body.add_namespace("imagenet_browser", LINK_RELATIONS_URL)
        body.add_control("self", url_for("api.synsetcollection"))
        body.add_control_add_synset()

        synsets = Synset.query.order_by(Synset.wnid).offset(start)

        if start >= SYNSET_PAGE_SIZE:
            body.add_control("prev", url_for("api.synsetcollection") + "?start={}".format(start - SYNSET_PAGE_SIZE))
        if synsets.count() > SYNSET_PAGE_SIZE:
            body.add_control("next", url_for("api.synsetcollection") + "?start={}".format(start + SYNSET_PAGE_SIZE))

        body["items"] = []
        for synset in synsets.limit(SYNSET_PAGE_SIZE):
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
        """
        Add a new synset and return its location in the response headers.
        The synset representation must be valid against the synset schema.
        """
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
                "Synset with WordNet ID of '{}' already exists".format(request.json["wnid"])
            )

        return Response(status=201, headers={
            "Location": url_for("api.synsetitem", wnid=request.json["wnid"])
        })

class SynsetItem(Resource):
    """
    Subclass of Resource that defines the HTTP method handlers for the SynsetItem resource.
    Error scenarios for the various methods are described in the calls to create_error_response, or alternatively, in the resource tests.
    A synset identified by its WordNet ID.
    """

    def get(self, wnid):
        """
        Build and return the synset representation.
        """
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
        body.add_control("imagenet_browser:synsethyponymcollection", url_for("api.synsethyponymcollection", wnid=wnid))
        body.add_control("imagenet_browser:synsetimagecollection", url_for("api.synsetimagecollection", wnid=wnid))

        return Response(json.dumps(body), 200, mimetype=MASON)

    def put(self, wnid):
        """
        Replace the synset representation with a new one.
        Must validate against the synset schema.
        """
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
                "Synset with WordNet ID of '{}' already exists".format(request.json["wnid"])
            )

        return Response(status=204)

    def delete(self, wnid):
        """
        Delete the synset and its associated images.
        """
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
    """
    Subclass of Resource that defines the HTTP method handlers for the SynsetHyponymCollection resource.
    Error scenarios for the various methods are described in the calls to create_error_response, or alternatively, in the resource tests.
    All hyponyms of a synset.
    """

    def get(self, wnid):
        """
        Build and return a list of all hyponyms of the synset.
        A list has SYNSET_PAGE_SIZE items with the starting index being controlled by the query parameter.
        As such, the next and prev controls become available when appropriate.
        """
        try:
            start = int(request.args.get("start", default=0))
        except ValueError:
            return create_error_response(
                400,
                "Invalid query parameter",
                "Query parameter 'start' must be an integer"
            )

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
        body.add_control("self", url_for("api.synsethyponymcollection", wnid=wnid) + "?start={}".format(start))
        body.add_control_add_hyponym(wnid=wnid)
        body.add_control("imagenet_browser:synsetitem", url_for("api.synsetitem", wnid=wnid))

        synset_hyponyms = synset.hyponyms[start:]

        if start >= SYNSET_PAGE_SIZE:
            body.add_control("prev", url_for("api.synsethyponymcollection", wnid=wnid) + "?start={}".format(start - SYNSET_PAGE_SIZE))
        if len(synset_hyponyms) > SYNSET_PAGE_SIZE:
            body.add_control("next", url_for("api.synsethyponymcollection", wnid=wnid) + "?start={}".format(start + SYNSET_PAGE_SIZE))

        body["items"] = []
        for synset_hyponym in synset_hyponyms[:SYNSET_PAGE_SIZE]:
            item = ImagenetBrowserBuilder(
                wnid=synset_hyponym.wnid,
                words=synset_hyponym.words,
                gloss=synset_hyponym.gloss
            )
            item.add_control("self", url_for("api.synsethyponymitem", wnid=wnid, hyponym_wnid=synset_hyponym.wnid))
            item.add_control("profile", SYNSET_PROFILE)
            body["items"].append(item)

        return Response(json.dumps(body), 200, mimetype=MASON)

    def post(self, wnid):
        """
        Add a new hyponym to the synset with the hyponym being a previously added synset and return its location in the response headers.
        The synset representation must be valid against a subset of the synset schema that only requires the WordNet ID.
        """
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
            validate(request.json, Synset.get_schema(wnid_only=True))
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))

        synset_hyponym = Synset.query.filter_by(wnid=request.json["wnid"]).first()
        if not synset_hyponym:
            return create_error_response(
                404,
                "Not found",
                "No synset with WordNet ID of '{}' found".format(request.json["wnid"])
            )

        try:
            synset.hyponyms.index(synset_hyponym)
        except ValueError:
            pass
        else:
            return create_error_response(
                409,
                "Already exists",
                "Synset hyponym with WordNet ID of '{}' already exists".format(request.json["wnid"])
            )

        synset.hyponyms.append(synset_hyponym)
        db.session.commit()

        return Response(status=201, headers={
            "Location": url_for("api.synsethyponymitem", wnid=wnid, hyponym_wnid=request.json["wnid"])
        })

class SynsetHyponymItem(Resource):
    """
    Subclass of Resource that defines the HTTP method handlers for the SynsetHyponymItem resource.
    Error scenarios for the various methods are described in the calls to create_error_response, or alternatively, in the resource tests.
    A hyponym of a synset identified by its WordNet ID.
    """

    def get(self, wnid, hyponym_wnid):
        """
        Build and return the hyponym representation.
        """
        synset = Synset.query.filter_by(wnid=wnid).first()
        if not synset:
            return create_error_response(
                404,
                "Not found",
                "No synset with WordNet ID of '{}' found".format(wnid)
            )

        synset_hyponym = Synset.query.filter_by(wnid=hyponym_wnid).first()

        try:
            synset.hyponyms.index(synset_hyponym)
        except ValueError:
            return create_error_response(
                404,
                "Not found",
                "No synset hyponym with WordNet ID of '{}' found".format(hyponym_wnid)
            )

        body = ImagenetBrowserBuilder(
            wnid=hyponym_wnid,
            words=synset_hyponym.words,
            gloss=synset_hyponym.gloss
        )
        body.add_namespace("imagenet_browser", LINK_RELATIONS_URL)
        body.add_control("self", url_for("api.synsethyponymitem", wnid=wnid, hyponym_wnid=hyponym_wnid))
        body.add_control("profile", SYNSET_PROFILE)
        body.add_control("collection", url_for("api.synsethyponymcollection", wnid=wnid))
        body.add_control_delete_hyponym(wnid=wnid, hyponym_wnid=hyponym_wnid)

        return Response(json.dumps(body), 200, mimetype=MASON)

    def delete(self, wnid, hyponym_wnid):
        """
        Delete the hyponym.
        """
        synset = Synset.query.filter_by(wnid=wnid).first()
        if not synset:
            return create_error_response(
                404,
                "Not found",
                "No synset with WordNet ID of '{}' found".format(wnid)
            )

        try:
            synset.hyponyms.remove(Synset.query.filter_by(wnid=hyponym_wnid).first())
        except ValueError:
            return create_error_response(
                404,
                "Not found",
                "No synset hyponym with WordNet ID of '{}' found".format(hyponym_wnid)
            )

        db.session.commit()

        return Response(status=204)
