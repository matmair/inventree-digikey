from operator import mod

from django.db import models


class TestMdl(models.Model):

    test = models.CharField('abc', max_length=255)
    bb = models.CharField('abc', max_length=255, null=True)
