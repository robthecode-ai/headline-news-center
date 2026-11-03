from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ApprovedArticleLog, Article
from .permissions import editable_articles, visible_articles
from .serializers import ApprovalLogRequestSerializer, ArticleSerializer


@api_view(["GET", "POST"])
def article_list(request):
    """List approved articles or accept a journalist's submission."""
    if request.method == "GET":
        articles = visible_articles(request.user).order_by(
            "-created_at",
        )

        serializer = ArticleSerializer(
            articles,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    if not request.user.groups.filter(name="Journalist").exists():
        return Response(
            {"detail": "Journalists only."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ArticleSerializer(
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(author=request.user, approved=False)

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PUT", "DELETE"])
def article_detail(request, pk):
    """Retrieve approved content or manage an authorised article."""
    if request.method == "GET":
        article = get_object_or_404(
            visible_articles(request.user),
            pk=pk,
        )

        serializer = ArticleSerializer(
            article,
            context={"request": request},
        )
        return Response(serializer.data)

    if not request.user.groups.filter(
        name__in=("Journalist", "Editor"),
    ).exists():
        return Response(
            {"detail": "Journalists and editors only."},
            status=status.HTTP_403_FORBIDDEN,
        )

    article = get_object_or_404(
        editable_articles(request.user),
        pk=pk,
    )

    if request.method == "DELETE":
        article.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ArticleSerializer(
        article,
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(
        approved=False,
        email_sent=False,
        api_logged=False,
    )

    return Response(serializer.data)


@api_view(["GET"])
def subscribed_articles(request):
    """Return approved articles matching the authenticated reader."""
    if not request.user.groups.filter(name="Reader").exists():
        return Response(
            {"detail": "Readers only."},
            status=status.HTTP_403_FORBIDDEN,
        )

    articles = Article.objects.filter(
        Q(publisher__in=request.user.subscribed_publishers.all())
        | Q(author__in=request.user.subscribed_journalists.all()),
        approved=True,
    ).distinct().order_by("-created_at")

    serializer = ArticleSerializer(
        articles,
        many=True,
        context={"request": request},
    )
    return Response(serializer.data)


@api_view(["POST"])
def approved_article_log(request):
    """Log an article published by its authorised editor or author."""
    if not request.user.groups.filter(
        name__in=("Editor", "Journalist"),
    ).exists():
        return Response(
            {"detail": "Journalists and editors only."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ApprovalLogRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    articles = editable_articles(request.user)

    if request.user.groups.filter(name="Journalist").exists():
        articles = articles.filter(publisher__isnull=True)

    article = get_object_or_404(
        articles,
        pk=serializer.validated_data["article_id"],
        approved=True,
    )

    log, created = ApprovedArticleLog.objects.update_or_create(
        article=article,
        defaults={
            "title": article.title,
            "content": article.content,
        },
    )

    response_status = (
        status.HTTP_201_CREATED
        if created
        else status.HTTP_200_OK
    )

    return Response(
        {
            "id": log.pk,
            "article_id": article.pk,
            "title": log.title,
            "logged_at": log.logged_at,
        },
        status=response_status,
    )
