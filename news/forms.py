from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q

from .models import Article, Newsletter, Publisher, User


class RegistrationForm(UserCreationForm):
    """Register an application account without admin privileges."""

    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        initial="reader",
    )

    def clean_email(self):
        """Normalise the email and reject an existing address."""
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email address already exists."
            )

        return email

    class Meta(UserCreationForm.Meta):
        """Expose account details and the application role."""

        model = User
        fields = (
            "username",
            "email",
            "role",
            "password1",
            "password2",
        )


class ArticleForm(forms.ModelForm):
    """Collect article content without exposing approval or ownership."""

    class Meta:
        """Define the editable article fields."""

        model = Article
        fields = ("title", "content", "publisher", "image", "caption")

    def __init__(self, *args, user, **kwargs):
        """Limit publisher choices to the user's organisations."""
        super().__init__(*args, **kwargs)

        if user.role == "journalist":
            publishers = Publisher.objects.filter(journalists=user)
        elif user.role == "editor":
            publishers = Publisher.objects.filter(editors=user)
        else:
            publishers = Publisher.objects.none()

        self.fields["publisher"].queryset = publishers.distinct()


class SubscriptionForm(forms.ModelForm):
    """Allow readers to choose publishers and journalists to follow."""

    class Meta:
        """Expose only subscription relationships."""

        model = User
        fields = (
            "subscribed_publishers",
            "subscribed_journalists",
        )


class NewsletterForm(forms.ModelForm):
    """Collect newsletter details and authorised article selections."""

    class Meta:
        """Define the editable newsletter fields."""

        model = Newsletter
        fields = ("title", "description", "publisher", "articles")

    def __init__(self, *args, user, **kwargs):
        """Offer approved articles within the user's publishing scope."""
        super().__init__(*args, **kwargs)
        self.user = user

        if user.role == "journalist":
            publishers = Publisher.objects.filter(journalists=user)
        elif user.role == "editor":
            publishers = Publisher.objects.filter(editors=user)
            self.fields["publisher"].required = True
        else:
            publishers = Publisher.objects.none()

        self.fields["publisher"].queryset = publishers.distinct()

        articles = Article.objects.filter(
            approved=True,
            publisher__in=publishers,
        )

        if user.role == "journalist":
            articles = Article.objects.filter(
                Q(publisher__in=publishers)
                | Q(author=user, publisher__isnull=True),
                approved=True,
            )

        self.fields["articles"].queryset = articles.select_related(
            "publisher",
        ).distinct().order_by("-created_at")

        self.fields["articles"].help_text = (
            "Choose articles from the selected publisher. "
            "For an independent newsletter, choose only your own "
            "published independent articles."
        )

    def clean(self):
        """Reject article selections that do not match the newsletter."""
        cleaned_data = super().clean()

        if (
            "publisher" not in cleaned_data
            or "articles" not in cleaned_data
        ):
            return cleaned_data

        publisher = cleaned_data["publisher"]
        articles = cleaned_data["articles"]

        if publisher:
            invalid_articles = articles.exclude(publisher=publisher)
            message = (
                "All selected articles must belong to "
                "the selected publisher."
            )
        else:
            invalid_articles = articles.exclude(
                author=self.user,
                publisher__isnull=True,
            )
            message = (
                "Independent newsletters may contain only your own "
                "published independent articles."
            )

        if invalid_articles.exists():
            self.add_error("articles", message)

        return cleaned_data


class PublisherForm(forms.ModelForm):
    """Collect a publisher name without exposing team membership."""

    class Meta:
        """Define the editable publisher fields."""

        model = Publisher
        fields = ("name",)


class PublisherTeamForm(forms.ModelForm):
    """Manage a publisher's editors and journalists."""

    class Meta:
        """Expose publisher membership fields."""

        model = Publisher
        fields = ("editors", "journalists")
        widgets = {
            "editors": forms.CheckboxSelectMultiple(),
            "journalists": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, user, **kwargs):
        """Limit choices to active accounts with matching roles."""
        super().__init__(*args, **kwargs)
        self.user = user

        self.fields["editors"].queryset = User.objects.filter(
            role="editor",
            is_active=True,
        ).order_by("username")

        self.fields["journalists"].queryset = User.objects.filter(
            role="journalist",
            is_active=True,
        ).order_by("username")

        self.fields["editors"].help_text = (
            "Keep yourself selected so you retain access."
        )

    def clean_editors(self):
        """Prevent the current editor from removing their own access."""
        editors = self.cleaned_data["editors"]

        if not editors.filter(pk=self.user.pk).exists():
            raise forms.ValidationError(
                "Keep yourself selected as an editor."
            )

        return editors
