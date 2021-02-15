from django.contrib import admin
from apps.goods.models import GoodsType, GoodsSPU, GoodsSKU, GoodsImage,\
    IndexTypeGoodsBanner, IndexPromotionBanner, IndexGoodsBanner
from django.core.cache import cache


def celery_tasks_delay():
    from celery_tasks.tasks import generate_static_index_html
    generate_static_index_html.delay()  # 发出celery任务
    cache.delete('index_page_data')   # 清除缓存


class BaseModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        celery_tasks_delay()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        celery_tasks_delay()


class GoodsTypeAdmin(BaseModelAdmin):
    pass


class GoodsSPUAdmin(BaseModelAdmin):
    pass


class GoodsSKUAdmin(BaseModelAdmin):
    pass


class GoodsImageAdmin(BaseModelAdmin):
    pass


class IndexTypeGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexPromotionBannerAdmin(BaseModelAdmin):
    pass


class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass


admin.site.register(GoodsType, GoodsTypeAdmin)
admin.site.register(GoodsSPU, GoodsSPUAdmin)
admin.site.register(GoodsSKU, GoodsSKUAdmin)
admin.site.register(GoodsImage, GoodsImageAdmin)

admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBannerAdmin)
admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdmin)
admin.site.register(IndexGoodsBanner, IndexTypeGoodsBannerAdmin)




















