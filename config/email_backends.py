"""Development email backend — redirect all outgoing mail to a single inbox."""
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend


class DevelopmentRedirectEmailBackend(SMTPBackend):
    """
    Sends all email to DEV_EMAIL_OVERRIDE only (development safety).
    Original To/CC/BCC are appended to the text body for debugging.
    """

    def send_messages(self, email_messages):
        override = getattr(settings, 'DEV_EMAIL_OVERRIDE', None)
        if not override:
            return super().send_messages(email_messages)

        redirected = []
        for message in email_messages:
            original_to = list(message.to or [])
            original_cc = list(message.cc or [])
            original_bcc = list(getattr(message, 'bcc', None) or [])

            note = (
                '\n\n---\n'
                '[DEV] This alert was redirected for development.\n'
                f'Original TO: {", ".join(original_to) or "(none)"}\n'
                f'Original CC: {", ".join(original_cc) or "(none)"}\n'
                f'Original BCC: {", ".join(original_bcc) or "(none)"}\n'
            )
            message.body = (message.body or '') + note

            if message.subject and not message.subject.startswith('[DEV]'):
                message.subject = f'[DEV] {message.subject}'

            message.to = [override]
            message.cc = []
            message.bcc = []
            redirected.append(message)

        return super().send_messages(redirected)
