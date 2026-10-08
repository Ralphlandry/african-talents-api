import django_filters

from .models import Vote


class VoteFilter(django_filters.FilterSet):
    candidate = django_filters.UUIDFilter(field_name="candidate_id")
    phase = django_filters.UUIDFilter(field_name="phase_id")
    category = django_filters.UUIDFilter(field_name="candidate__category_id")
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = Vote
        fields = ["candidate", "phase", "category", "source"]
