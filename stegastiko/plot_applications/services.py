from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import Community
from core.services import get_setting
from plot_applications.models import PlotApplication

PROTOCOL_NUMBER_MAX_ATTEMPTS = 5


def _protocol_base(community) -> str:
    if not community.community_folder_code:
        raise ValidationError("Η κοινότητα δεν έχει communityFolderCode.")
    prefix = get_setting("plotApplicationProtocolPrefix", "Π3-")
    return f"{prefix}{community.community_folder_code}-"


def generate_protocol_number(community, offset: int = 0) -> str:
    """Αρ. Πρωτοκόλλου («Για Επίσημη Χρήση»): πρόθεμα + κωδικός Κοινότητας + αύξων αριθμός.

    Χρησιμοποιείται στους Καταλόγους Δικαιούχων (Ενότ. 6, 7). Ο αύξων συνεχίζει από τον
    μεγαλύτερο ήδη εκδοθέντα, ώστε διαγραμμένες αιτήσεις να μην επαναχρησιμοποιούν αριθμό.
    """
    community = Community.objects.select_for_update().get(pk=community.pk)
    base = _protocol_base(community)
    highest = 0
    for number in PlotApplication.objects.filter(protocol_number__startswith=base).values_list(
        "protocol_number", flat=True
    ):
        suffix = number[len(base):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    digits = int(get_setting("folderSequenceDigits", "3"))
    return f"{base}{str(highest + 1 + offset).zfill(digits)}"


def save_with_new_protocol_number(application: PlotApplication) -> PlotApplication:
    for attempt in range(PROTOCOL_NUMBER_MAX_ATTEMPTS):
        application.protocol_number = generate_protocol_number(application.community, attempt)
        try:
            with transaction.atomic():
                application.save()
        except IntegrityError as exc:
            if "protocol_number" not in str(exc):
                raise
            application.pk = None
            application._state.adding = True
            continue
        return application
    raise ValidationError("Δεν ήταν δυνατή η απόδοση μοναδικού Αρ. Πρωτοκόλλου. Δοκιμάστε ξανά.")
