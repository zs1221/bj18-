from django.shortcuts import render
from django.views.generic import View
from django.http import JsonResponse
from apps.goods.models import GoodsSKU
from django_redis import get_redis_connection
from utils.mixin import LoginRequiredMixin


class CartAddView(View):
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 5, 'errmsg': '用户没有登录'})
        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')
        print(sku_id, count)
        # 数据校验
        if not all([sku_id, count]):
            return JsonResponse({'res': 0, 'errmsg': '数据不完整'})

        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({"res": 1, 'errmsg': '商品数目出错'})

        # 商品是否存在：
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except Exception as e:
            return JsonResponse({'res': 6, 'errmsg': '查不到商品'})

        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        print('user_id: ', user.id)
        # 读取已存在的商品数目
        cart_count = conn.hget(cart_key, sku_id)
        # 进行累加数目
        if cart_count:
            count += int(cart_count)
        # 校验商品库存
        if count > sku.stock:
            return JsonResponse({'res': 3, 'errmsg': '商品数量不足'})

        # 再重新设置塞到数据库
        conn.hset(cart_key, sku_id, count)  # 没有商品就重新设置，否则添加

        total_count = conn.hlen(cart_key)
        # 返回应答
        return JsonResponse({'res': 4, 'total_count': total_count, 'message': '添加成功'})


class CartInfoView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        cart_dict = conn.hgetall(cart_key)  # 字典数据 商品id: 商品数量
        skus = []
        total_count = 0
        total_price = 0
        for sku_id, count in cart_dict.items():
            # 根据商品的id获取商品的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算商品的小计
            amount = sku.price * int(count)
            # 动态给sku对象增加一个属性count，保存购物车中对应商品的数量
            sku.amount = amount
            sku.count = count
            # 添加
            skus.append(sku)
            # 累加计算商品的总数目和总价格
            total_count += int(count)
            total_price += amount

        context = {'total_count': total_count,
                   'total_price': total_price,
                   'skus': skus}

        return render(request, 'cart.html', context)


# 采用ajax post 请求
# 前端需要传递的参数:商品id， 更新的商品数量count
# /cart/update
class CartUpdateView(View):
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 5, 'errmsg': '用户没有登录'})
        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')
        print(sku_id)
        # 数据校验
        if not all([sku_id, count]):
            return JsonResponse({'res': 0, 'errmsg': '数据不完整'})

        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({"res": 1, 'errmsg': '商品数目出错'})

        # 商品是否存在：
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except Exception as e:
            return JsonResponse({'res': 6, 'errmsg': '查不到商品'})

        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 校验商品库存
        if count > sku.stock:
            return JsonResponse({'res': 3, 'errmsg': '商品数量不足'})

        # 更新
        conn.hset(cart_key, sku_id, count)

        # 计算商品总件数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        return JsonResponse({'res': 2, 'total_count': total_count, 'message': '添加成功'})


# 采用ajax post 请求
# 前端需要传递的参数:商品id
# /cart/delete
class CartDeleteView(View):
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 1, 'errmsg': '用户没有登录'})
        # 接收数据
        sku_id = request.POST.get('sku_id')
        print('sku_id', sku_id)
        # 数据校验
        if not all([sku_id]):
            return JsonResponse({'res': 2, 'errmsg': '数据不完整'})

        # 商品是否存在：
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except Exception as e:
            return JsonResponse({'res': 3, 'errmsg': '查不到商品'})

        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 删除
        conn.hdel(cart_key, sku_id)

        # 计算商品总件数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 4, 'total_count': total_count, 'message': '添加成功'})




































