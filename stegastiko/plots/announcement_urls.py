from django.urls import path

from plots import announcement_views as views

app_name = "announcements"

urlpatterns = [
    path("", views.announcement_list, name="list"),
    path("new/", views.announcement_create, name="create"),
    path("<int:pk>/", views.announcement_detail, name="detail"),
    path("<int:pk>/regenerate/", views.announcement_regenerate, name="regenerate"),
    path("<int:pk>/publish/", views.announcement_publish, name="publish"),
    path("<int:pk>/publications/new/", views.publication_form, name="publication_create"),
    path(
        "<int:pk>/publications/<int:publication_id>/edit/",
        views.publication_form,
        name="publication_edit",
    ),
    path(
        "<int:pk>/publications/<int:publication_id>/delete/",
        views.publication_delete,
        name="publication_delete",
    ),
]
