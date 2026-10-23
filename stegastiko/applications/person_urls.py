from django.urls import path

from applications import person_views as views

app_name = "persons"

urlpatterns = [
    path("", views.person_list, name="list"),
    path("new/", views.person_create, name="create"),
    path("<int:pk>/", views.person_detail, name="detail"),
    path("<int:pk>/applications-order/", views.person_applications_reorder, name="applications_reorder"),
    path("<int:pk>/delete/", views.person_delete, name="delete"),
]
