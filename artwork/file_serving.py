"""Helpers for streaming artwork files from local disk or S3."""
import mimetypes

from django.http import FileResponse, Http404


def stream_attachment(attachment, as_attachment=False):
    """Return a FileResponse for an ArtworkAttachment, works with any storage backend."""
    if not attachment.file:
        raise Http404('File not found')

    filename = attachment.original_filename or attachment.file.name.split('/')[-1]
    content_type = (
        attachment.mime_type
        or mimetypes.guess_type(filename)[0]
        or 'application/octet-stream'
    )

    file_handle = attachment.file.open('rb')
    response = FileResponse(file_handle, content_type=content_type)
    disposition = 'attachment' if as_attachment else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    return response
