from flask import Flask, request, Response
from kik import KikApi, KikError, Configuration
from kik.messages import messages_from_json, TextMessage, SuggestedResponseKeyboard, TextResponse
import requests

BOT_USERNAME = '...'
BOT_API_KEY = '...'
BOT_WEBHOOK = '...'
BOT_ZAPHOOK = '...'

POST_USER = '...'
POST_PASSWORD = '...'

FEELS_ADMIN = '...'
FEELS_RECIPIENT = '...'

BUTTON_REQUEST = 'Get more feels'

app = Flask(__name__)
kik = KikApi(BOT_USERNAME, BOT_API_KEY)
kik.set_configuration(Configuration(webhook=BOT_WEBHOOK))


@app.route('/incoming', methods=['POST'])
def incoming():
    if not kik.verify_signature(request.headers.get('X-Kik-Signature'), request.get_data()):
        return Response(status=403)

    messages = messages_from_json(request.json['messages'])

    for message in messages:
        if isinstance(message, TextMessage):
            if message.from_user == FEELS_RECIPIENT:
                if message.body == BUTTON_REQUEST:
                    r = requests.post(BOT_ZAPHOOK, data={
                        'message': 'As requested, another message in case you need more feels:',
                        'noFeels': 'false'
                    })
                    if r.status_code != 200:
                        return Response(status=504)
                else:
                    reply = TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Sorry, I'm not smart enough to understand. Try looking for the auto response "
                             "buttons or tell me me '" + BUTTON_REQUEST + "'."
                    )
                    build_recipient_keyboard(reply)
                    kik.send_messages([reply])

            elif message.from_user == FEELS_ADMIN:
                reply = TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body='Admin functions are not currently implemented.'
                )
                kik.send_messages([reply])

            else:
                reply = TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body='You are not a recognised user for this bot. Sorry.'
                )
                kik.send_messages([reply])

    return Response(status=200)


@app.route('/message', methods=['POST'])
def from_zapier():
    try:
        auth = request.authorization
        if auth.username != POST_USER or auth.password != POST_PASSWORD:
            return Response(status=403)
    except AttributeError:
        return Response(status=401)

    post = request.form
    body = post['message']
    no_feel = bool_from_string(post['noFeels'])
    if not no_feel:
        body += '\n\n' + post['feelsComment'] + '\n' + '  --' + post['from'] + ' (' + post['feelsDate'] + ')'

    message = TextMessage(
        to=FEELS_RECIPIENT,
        body=body
    )
    build_recipient_keyboard(message)

    try:
        kik.send_messages([message])
    except KikError:
        return Response(status=500)

    return Response(status=200)


def build_recipient_keyboard(message):
    if message is None:
        return

    message.keyboards.append(
        SuggestedResponseKeyboard(
            to=FEELS_RECIPIENT,
            hidden=False,
            responses=[TextResponse(BUTTON_REQUEST)]
        )
    )


def bool_from_string(boolean):
    return boolean[0].upper() == 'T'


if __name__ == '__main__':
    app.run()
