from kik import KikError
from kik.messages import TextMessage, SuggestedResponseKeyboard


class MessageQueue:
    def __init__(self, config, kik):
        self.config = config
        self.kik = kik
        self.queue = {}

    def add_message(self, to, body, chat_id=None, keyboards=None):
        """
        ???
        :param to:
        :param body:
        :param chat_id:
        :param keyboards:
        :return:
        """
        if chat_id is not None:
            message = TextMessage(
                to=to,
                chat_id=chat_id,
                body=body
            )
        else:
            message = TextMessage(
                to=to,
                body=body
            )

        if keyboards is not None:
            self._build_keyboard(message, to, keyboards)

        try:
            self.queue[to].append(message)
        except KeyError:
            self.queue[to] = [message]

    def send_all(self):
        """
        Send all messages within the queue and make the queue empty again
        :return: 200 if successful, 202 if kik returned an error (based upon http status codes)
        """
        queue = self.queue
        count = {}
        self.queue = {}
        for person in queue.keys():
            count[person] = 0

        # Function within a function
        # For use with the while loop, to save have to do these tests within the loop itself (looks messy)
        def count_unprocessed():
            result = False
            for c in count:
                if count[c] < len(queue[c]):
                    result = True
            return result

        while count_unprocessed():
            sending = []
            for person in queue:
                # Should never exceed 25, but playing safe in case of other errors
                if len(sending) >= 25:
                    break

                add = min(5, 25-len(sending))
                if count[person] < len(queue[person]):
                    # Add the next messages by getting the appropriate splice of the queue
                    # Based upon rate limit of 5 messages per person, 25 messages per batch
                    sending += queue[person][count[person]:count[person] + add]
                    count[person] += add

            # Be certain there is actually something to send
            if len(sending) > 0:
                try:
                    self.kik.send_messages(sending)
                except KikError as e:
                    # Log the error, will appear in apache error logs when running under wsgi
                    error_handler(self, e, queue, count, sending)
                    # Also need to make certain we don't cause Kik server to go into a loop of resending the message
                    # Returning 500 would cause the message to be resent up to a total of 4 times.
                    # Hence 202 is a received and being processed but no guarantee of any outcome.
                    #
                    # NOTE: returning 202 has not actually been tested yet (to confirm it doesn't cause loop).
                    # Other option might be to return 504 instead.
                    return 202

        return 200

    @staticmethod
    def _build_keyboard(message, to, responses):
        """
        Build the keyboard for the provided message with the specified responses.
        :param message: The message to have the responses added to it.
        :param to: The recipient of the message.
        :param responses: An array with Kik keyboard responses.
        :return: Nothing (message object directly modified to include the keyboard)
        """
        if len(responses) > 0:
            message.keyboards.append(
                SuggestedResponseKeyboard(
                    to=to,
                    hidden=False,
                    responses=responses
                )
            )


def error_handler(message_queue, e, queue, count, sending):
    """
    Error handler called in the event of problems sending the message batch.

    The aim being to log as many details of the surrounding circumstances, not just the error itself - this will only be
    called if the Kik API or the Kik servers reject the bundle of messages, which could mean a malformed message or
    server error. So, if this happens, we need to have the context of the call, not just the error.

    :param message_queue:
    :param e:
    :param queue:
    :param count:
    :param sending:
    :return:
    """
    print("Error encountered during message sending.")
    print("Sending list length: {}".format(len(sending)))
    print("Queue: {}".format(queue))
    print("Count: {}".format(count))
    print("Sending: {}". format(sending))
    print(e)
    try:
        message_queue.kik.send_messages(TextMessage(
            to=message_queue.config['admin'],
            body="Error encountered during message send. See apache logs for details."
        ))
        print("Admin notification sent.")
    except KikError:
        print("Admin notify failed.")
