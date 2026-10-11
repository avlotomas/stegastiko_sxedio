"""Download of the files kept on a case folder."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header

from cases.models import Case
from cases.services import attachment_owning_section, case_attachments
from core.function_catalog import case_section_function
from core.permissions import access_required, require_access


@access_required("cases")
def case_attachment_download(request, pk, attachment_id):
    """Download a case file: 3.1 plot, 4.4 / 7.2 / 7.3 case, 5 / 7.4 consultation or 6.7 files."""
    case = get_object_or_404(Case, pk=pk)
    attachment = get_object_or_404(
        case_attachments(case).select_related("content_type"), pk=attachment_id
    )
    require_access(request.user, case_section_function(attachment_owning_section(attachment)))
    response = HttpResponse(bytes(attachment.data), content_type=attachment.content_type_name)
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=attachment.filename
    )
    return response
