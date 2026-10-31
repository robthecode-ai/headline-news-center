from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from . import api_views


app_name = "news_api"

urlpatterns = [
    path("token/", obtain_auth_token, name="token"),
    path("articles/", api_views.article_list, name="article_list"),
    path(
        "articles/subscribed/",
        api_views.subscribed_articles,
        name="subscribed_articles",
    ),
    path(
        "articles/<int:pk>/",
        api_views.article_detail,
        name="article_detail",
    ),
    path(
        "approved/",
        api_views.approved_article_log,
        name="approved_article_log",
    ),
]
