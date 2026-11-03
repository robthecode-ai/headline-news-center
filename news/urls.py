from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


app_name = "news"

urlpatterns = [
    path("", views.home, name="home"),
    path("articles/<int:pk>/", views.article_detail, name="article_detail"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="news/login.html",
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path("register/", views.register, name="register"),
    path("my-articles/", views.my_articles, name="my_articles"),
    path("review-queue/", views.review_queue, name="review_queue"),
    path("articles/new/", views.article_create, name="article_create"),
    path("articles/<int:pk>/edit/", views.article_edit, name="article_edit"),
    path(
        "articles/<int:pk>/review/",
        views.article_review,
        name="article_review",
    ),
    path(
        "articles/<int:pk>/approve/",
        views.article_approve,
        name="article_approve",
    ),
    path(
        "articles/<int:pk>/delete/",
        views.article_delete,
        name="article_delete",
    ),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path(
        "my-feed/",
        views.subscribed_articles,
        name="subscribed_articles",
    ),
    path("newsletters/", views.newsletter_list, name="newsletter_list"),
    path(
        "newsletters/new/",
        views.newsletter_create,
        name="newsletter_create",
    ),
    path(
        "newsletters/<int:pk>/",
        views.newsletter_detail,
        name="newsletter_detail",
    ),
    path(
        "newsletters/<int:pk>/edit/",
        views.newsletter_edit,
        name="newsletter_edit",
    ),
    path(
        "newsletters/<int:pk>/delete/",
        views.newsletter_delete,
        name="newsletter_delete",
    ),
    path(
        "manage-articles/",
        views.manage_articles,
        name="manage_articles",
    ),
    path(
        "publishers/new/",
        views.publisher_create,
        name="publisher_create",
    ),
    path(
        "my-publishers/",
        views.my_publishers,
        name="my_publishers",
    ),
    path(
        "publishers/<int:pk>/team/",
        views.publisher_team,
        name="publisher_team",
    ),
    path(
        "articles/<int:pk>/publish/",
        views.article_publish,
        name="article_publish",
    ),
]
