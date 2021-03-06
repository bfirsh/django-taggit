from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.fields.related import ManyToManyRel
from django.db.models.query_utils import QueryWrapper

from taggit.forms import TagField
from taggit.models import Tag, TaggedItem
from taggit.utils import require_instance_manager


class TaggableRel(ManyToManyRel):
    def __init__(self):
        self.to = TaggedItem
        self.related_name = None
        self.limit_choices_to = {}
        self.symmetrical = True
        self.multiple = True
        self.through = None


class TaggableManager(object):
    def __init__(self):
        self.rel = TaggableRel()
        self.editable = True
        self.unique = False
        self.creates_table = False
        self.db_column = None
        self.choices = None
        self.creation_counter = models.Field.creation_counter
        models.Field.creation_counter += 1
    
    def __get__(self, instance, type):
        manager = _TaggableManager()
        manager.model = type
        if instance is None:
            manager.object_id = None
        else:
            manager.object_id = instance.pk
        return manager
    
    def contribute_to_class(self, cls, name):
        self.name = self.column = name
        self.model = cls
        cls._meta.add_field(self)
        setattr(cls, name, self)

    def save_form_data(self, instance, value):
        getattr(instance, self.name).set(*value)
    
    def get_db_prep_lookup(self, lookup_type, value):
        if lookup_type not in  ("in", "exact"):
            raise ValueError("You can't do lookups other than \"in\" and \"exact\" on Tags")
        if lookup_type == "exact":
            value = [value]
        if all(isinstance(v, Tag) for v in value):
            qs = TaggedItem.objects.filter(tag__in=value)
        elif all(isinstance(v, basestring) for v in value):
            qs = TaggedItem.objects.filter(tag__name__in=value)
        elif all(isinstance(v, (int, long)) for v in value):
            # This one is really ackward, just don't do it.  The ORM does it
            # for deletes, but no one else gets to.
            qs = TaggedItem.objects.filter(pk__in=value)
        else:
            # Fucking flip-floppers.
            raise ValueError("You can't combine Tag objects and strings.  '%s' was provided." % value)
        sql, params = qs.values_list("pk", flat=True).query.as_sql()
        return QueryWrapper(("(%s)" % sql), params)
    
    def formfield(self, form_class=TagField, **kwargs):
        defaults = {
            "label": "Tags",
            "help_text": "A comma seperated list of tags."
        }
        defaults.update(kwargs)
        return form_class(**kwargs)
    
    def value_from_object(self, instance):
        return ", ".join(map(unicode, getattr(instance, self.name).all()))
    
    def related_query_name(self):
        return None
    
    def m2m_reverse_name(self):
        return "id"
    
    def m2m_column_name(self):
        return "object_id"
    
    def db_type(self):
        return None
    
    def m2m_db_table(self):
        return self.rel.to._meta.db_table
    
    def extra_filters(self, pieces, pos, negate):
        if negate:
            return []
        prefix = "__".join(pieces[:pos+1])
        return [("%s__content_type" % prefix, ContentType.objects.get_for_model(self.model))]


class _TaggableManager(models.Manager):
    def get_query_set(self):
        ct = ContentType.objects.get_for_model(self.model)
        if self.object_id is not None:
            return Tag.objects.filter(items__object_id=self.object_id, 
                items__content_type=ct)
        else:
            return Tag.objects.filter(items__content_type=ct).distinct()
    
    @require_instance_manager
    def add(self, *tags):
        for tag in tags:
            if not isinstance(tag, Tag):
                tag, _ = Tag.objects.get_or_create(name=tag)
            TaggedItem.objects.create(object_id=self.object_id, 
                content_type=ContentType.objects.get_for_model(self.model), tag=tag)
    
    @require_instance_manager
    def set(self, *tags):
        self.clear()
        self.add(*tags)
    
    @require_instance_manager
    def remove(self, *tags):
        TaggedItem.objects.filter(object_id=self.object_id, 
            content_type=ContentType.objects.get_for_model(self.model)).filter(
            tag__name__in=tags).delete()
    
    @require_instance_manager
    def clear(self):
        TaggedItem.objects.filter(object_id=self.object_id,
            content_type=ContentType.objects.get_for_model(self.model)).delete()
    
    def most_common(self):
        return self.get_query_set().annotate(
            num_times=models.Count('items')
        ).order_by('-num_times')
