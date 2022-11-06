from flask import Flask
from flask_restful import Resource, Api, reqparse
import scryfall


def create_app(name):
    app = Flask(name)

    # Initiate
    scryfall.init_db()

    return app


app = create_app(__name__)
api = Api(app)


@app.route("/", methods=["GET"])
def home():
    return "<h1>Cockatrice card api</h1><p>This site is a prototype API for cockatrice card image fetching.</p>"


class Card(Resource):
    # methods go here
    def get(self):
        if scryfall.db_loading_lock.locked():
            return {"error": "card database is still loading... please retry"}, 500
        else:
            parser = reqparse.RequestParser()  # initialize

            parser.add_argument("name", required=True, location="args")
            parser.add_argument("lang", required=True, location="args")

            args = parser.parse_args()  # parse arguments to dictionary

            alternatives = scryfall.get_cards(name=args["name"])
            max_score = 0
            selected_print = []
            for card in alternatives:
                score = scryfall.evaluate_card_score(card)
                if score > max_score:
                    max_score = score
                    selected_print = card

            return selected_print, 200  # return data and 200 OK code


api.add_resource(Card, "/card")  # '/users' is our entry point


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")  # run our Flask app
