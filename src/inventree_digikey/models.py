"""Models for inventree-digikey."""

from django.db import models


class TestMdl(models.Model):
    """Testmodel."""

    test = models.CharField('abc', max_length=255)
    bb = models.CharField('abc', max_length=255, null=True)
