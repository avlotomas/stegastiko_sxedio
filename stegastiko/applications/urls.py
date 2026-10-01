from django.urls import path

from applications import views

app_name = "applications"

urlpatterns = [
    path("", views.application_list, name="list"),
    path("new/", views.application_create, name="create"),
    path("import/", views.application_import, name="import"),
    path("<int:pk>/", views.application_detail, name="detail"),
    path("<int:pk>/edit/", views.application_edit, name="edit"),
    path("person-lookup/", views.person_lookup, name="person_lookup"),
    path("person-compare/", views.person_compare, name="person_compare"),
]
