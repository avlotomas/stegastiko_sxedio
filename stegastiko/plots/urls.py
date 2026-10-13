from django.urls import path

from plots import views

app_name = "plots"

urlpatterns = [
    path("", views.plot_list, name="list"),
    path("new/", views.plot_create, name="create"),
    path("<int:pk>/", views.plot_detail, name="detail"),
    path("<int:pk>/delete/", views.plot_delete, name="delete"),
]
