from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from apps.goods.models import GoodsType, GoodsSKU, \
    IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
from django_redis import get_redis_connection
from django.core.cache import cache
from apps.order.models import OrderGoods
from django.core.paginator import Paginator


class IndexView(View):
    def get(self, request):
        """首页"""
        # 尝试获取缓存
        context = cache.get("index_page_data")
        print('加载缓存内容:----------------', context)
        if context is None:
            print('-------------设置缓存---------->    None')
            # 获取商品种类信息
            types = GoodsType.objects.all()

            # 获取首页轮播商品信息
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')

            # 获取首页促销商品信息
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

            # 获取分类商品展示信息
            for type in types:
                # 获取type种类首页分类商品的图片展示信息
                image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')

                # 获取type种类首页分类商品的文字展示信息
                title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

                # 动态给type增加属性
                type.image_banners = image_banners
                type.title_banners = title_banners

            context = {
                'types': types,
                'goods_banners': goods_banners,
                'promotion_banners': promotion_banners}
            # 设置缓存3秒有效期，便于调试
            cache.set('index_page_data', context, 3600*7)
        # cache.set('index_page_data', context, 7*24*3600)

        # 获取购物车中商品数量
        user = request.user
        print('缓存user.id:', user, ' ', user.id)
        cart_count = 0
        if user.is_authenticated():
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)
        # 组织上下文
        context.update(cart_count=cart_count)
        return render(request, 'index.html', context)


class DetailView(View):
    def get(self, request, goods_id):
        try:  # 获取商品id
            sku = GoodsSKU.objects.get(id=goods_id)
            print('sku', sku)
        except Exception:  # 如果没有返回首页
            return redirect(reverse('goods:index'))
        #  获取所有商品分类信息
        types = GoodsType.objects.all()
        # 获取商品评论信息
        sku_orders = OrderGoods.objects.filter(sku=sku).exclude(comment="")  # 去除空评论
        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[0:3]  # 按时间排序

        same_spu_skus = GoodsSKU.objects.filter(goods_spu=sku.goods_spu).exclude(id=goods_id)
        # 获取购物车中商品数量
        user = request.user
        cart_count = 0
        if user.is_authenticated():
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

            # 添加用户历史浏览记录
            conn = get_redis_connection('default')
            history_key = 'history%d' % user.id
            # 移除列表中的goods_id
            conn.lrem(history_key, 0, goods_id)  # 0代表移除所有，history_key:用户  goods_id:商品
            # 把goods_id插入到列表的左侧
            conn.lpush(history_key, goods_id)
            # 只保存用户最新浏览的5条信息
            conn.ltrim(history_key, 0, 4)

        # 组织上下文
        context = {'sku': sku, 'types': types,
                   'sku_orders': sku_orders,
                   'new_skus': new_skus,
                   "same_skus": same_spu_skus,
                   'cart_count': cart_count}

        return render(request, 'detail.html', context)


# goods/list/type_id/页码?sort=排序方式  restful api 风格
class ListView(View):
    def get(self, request, type_id, page):
        a = GoodsType.objects.all()
        try:
            type = GoodsType.objects.get(id=type_id)
        except Exception:
            print('----------->种类不存在')
            return redirect(reverse('goods:index'))
        # 获取商品的分类信息
        types = GoodsType.objects.all()

        # 从前端获取用户输入的排序方式
        sort = request.GET.get('sort')

        if sort == 'price':
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        else:
            sort = "default"
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        paginator = Paginator(skus, 2)  # 每页显示1条

        try:
            page = int(page)
        except Exception as e:
            page = 1
        if page > paginator.num_pages:  # 页码总数
            page = 1
        skus_page = paginator.page(page)  # 返回当前页的数据

        # 进行页面的控制，页面上最多显示5个页码
        # 1.总页数小于5页，页面上显示所有页码
        # 2.如果当前页是前3页，显示1-5页
        # 3.如果当前页是后3页，显示后5页
        # 4.其它情况，显示  当前页的前2页，当前页，当前页后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages+1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages-4, num_pages+1)
        else:
            pages = range(page-2, page+3)

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=type).order_by('-create_time')[:2]

        # 获取购物车
        user = request.user
        cart_count = 0
        if user.is_authenticated():
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)
        # 组织上下文
        context = {'type': type, 'types': types,
                   'skus_page': skus_page,
                   'new_skus': new_skus,
                   'cart_count': cart_count,
                   'sort': sort,
                   'pages': pages}

        return render(request, 'list.html', context)



















