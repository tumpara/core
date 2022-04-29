from django.db import models


class Other(models.Model):
    baz = models.FloatField()


class Thing(models.Model):
    foo = models.CharField(max_length=10)
    bar = models.IntegerField(default=0)
    other = models.ForeignKey(Other, on_delete=models.CASCADE, null=True)
