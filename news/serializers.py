from rest_framework import serializers

from .models import Article, Newsletter, Publisher, User


class UserSerializer(serializers.ModelSerializer):
    """Expose public account information without credentials."""

    class Meta:
        """Define public, read-only user fields."""

        model = User
        fields = ("id", "username", "role")
        read_only_fields = fields


class PublisherSerializer(serializers.ModelSerializer):
    """Expose publisher information and team relationships."""

    class Meta:
        """Define read-only publisher fields."""

        model = Publisher
        fields = ("id", "name", "editors", "journalists")
        read_only_fields = fields


class ArticleSerializer(serializers.ModelSerializer):
    """Validate article content while protecting ownership and approval."""

    class Meta:
        """Define article fields and server-controlled values."""

        model = Article
        fields = (
            "id",
            "title",
            "content",
            "author",
            "created_at",
            "approved",
            "publisher",
            "image",
            "caption",
        )
        read_only_fields = (
            "id",
            "author",
            "created_at",
            "approved",
        )

    def validate_publisher(self, publisher):
        """Reject publisher assignments outside the user's membership."""
        if publisher is None:
            return publisher

        user = self.context["request"].user

        if user.groups.filter(name="Journalist").exists():
            allowed = publisher.journalists.filter(pk=user.pk).exists()
        elif user.groups.filter(name="Editor").exists():
            allowed = publisher.editors.filter(pk=user.pk).exists()
        else:
            allowed = False

        if not allowed:
            raise serializers.ValidationError(
                "You cannot assign articles to this publisher."
            )

        return publisher


class NewsletterSerializer(serializers.ModelSerializer):
    """Expose newsletter information and only approved story content."""

    articles = serializers.SerializerMethodField()

    class Meta:
        """Define read-only newsletter fields."""

        model = Newsletter
        fields = (
            "id",
            "title",
            "description",
            "created_at",
            "author",
            "publisher",
            "articles",
        )
        read_only_fields = fields

    def get_articles(self, newsletter):
        """Exclude articles that have returned to pending approval."""
        articles = newsletter.articles.filter(approved=True)

        return ArticleSerializer(
            articles,
            many=True,
            context=self.context,
        ).data


class ApprovalLogRequestSerializer(serializers.Serializer):
    """Validate the article identifier submitted for approval logging."""

    article_id = serializers.IntegerField(min_value=1)
