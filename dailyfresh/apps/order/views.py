from utils.mixin import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.conf import settings
from apps.goods.models import GoodsSKU
from django_redis import get_redis_connection
from apps.user.models import Address
from django.http import JsonResponse
from apps.order.models import OrderInfo, OrderGoods
from datetime import datetime
from django.db import transaction
from alipay import AliPay
import os


# /order/place
class OrderPlaceView(LoginRequiredMixin, View):
    """提交订单页面显示"""
    def post(self, request):
        """提交订单页面显示"""
        # 获取登录的用户
        user = request.user
        # 获取参数sku_ids
        sku_ids = request.POST.getlist('sku_ids')
        print(sku_ids, 'sku_ids')
        # 校验数据
        if not sku_ids:
            # 跳转到购物车页面
            return redirect(reverse('cart:show'))

        # 遍历sku_ids获取用户要购买的商品信息
        conn = get_redis_connection('default')
        cart_key = 'cart_{0}'.format(user.id)
        sku_cont = conn.hlen(cart_key)
        print(sku_cont, '---------------')
        total_count = 0
        total_price = 0
        skus = list()
        for sku_id in sku_ids:
            sku = GoodsSKU.objects.get(id=sku_id)
            print(sku, cart_key, sku_id)
            count = conn.hget(cart_key, sku_id)
            print(count)
            count = count.decode()
            # 计算商品小计
            amount = int(count) * sku.price
            # 动态给sku增加amount，count属性
            sku.count = count
            sku.amount = amount

            skus.append(sku)
            total_count += int(count)
            total_price += amount

        # 运费: 实际开发需要单独设计，这里写死
        transit_price = 10

        # 实付款
        total_pay = total_price + transit_price

        # 获取用户的收件地址
        addrs = Address.objects.filter(user=user)

        # 组织上下文
        sku_ids = ','.join(sku_ids)
        context = {
            'skus': skus,
            'total_count': total_count,
            'total_price': total_price,
            'transit_price': transit_price,
            'total_pay': total_pay,
            'addrs': addrs,
            'sku_ids': sku_ids,
            'sku_cont': sku_cont,
        }

        # 使用模板
        return render(request, 'place_order.html', context)


class OrderCommitView(View):
    @transaction.atomic  # 装饰之后里面的事情都在一个事务之中
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            print(addr_id, pay_method, sku_ids)
            return JsonResponse({"res": 1, 'errmsg': '非法的支付方式'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '无效支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Exception as e:
            return JsonResponse({'res': 3, 'errmsg': '地址无效'})

        # 创建订单核心业务
        order_id = datetime.now().strftime("%m%d%H%M%S") + str(user.id)
        # 运费
        transit_price = 10

        # 总数目，总金额
        total_count = 0
        total_price = 0

        # 设置保存点
        save_id = transaction.savepoint()

        # todo:向用户信息表df_order_info表中添加记录
        order = OrderInfo.objects.create(order_id=order_id,
                                         user=user,
                                         address=addr,
                                         pay_method=pay_method,
                                         total_count=total_count,
                                         total_price=total_price,
                                         transit_price=transit_price,)

        # todo:向用户商品表中df_order_goods添加记录
        sku_ids = sku_ids.split(',')  # '1,3,15,22'--->[1,3,15,22]  商品的id
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        for sku_id in sku_ids:

            for i in range(3):
                # 获取商品信息
                try:
                    sku = GoodsSKU.objects.get(id=sku_id)
                    # sku = GoodsSKU.objects.select_for_update().get(id=sku_id)  # 查询时上锁

                except:
                    transaction.savepoint_rollback(save_id)  # 回滚到保存点
                    print('回滚到保存点')
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                # 从redis中获取商品数量
                try:
                    count = int(conn.hget(cart_key, sku_id))
                except AttributeError:
                    print('NoneType对象没有属性decode')

                # todo: 判断商品的库存
                if count > sku.stock:
                    transaction.savepoint_rollback(save_id)  # 回滚到保存点
                    return JsonResponse({'res': 6, 'errmsg': '库存不足'})

                # 更新商品的库存和销量
                old_stock = sku.stock
                new_stock = old_stock - count
                new_sales = sku.sales + count
                import time
                time.sleep(0.1)
                res = GoodsSKU.objects.filter(id=sku_id, stock=old_stock).update(stock=new_stock, sales=new_sales)
                if res == 0:
                    if i == 2:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 7, 'errmsg': '下单失败，库存更改过'})
                    continue
                # todo:向用户商品表中df_order_goods添加记录
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)

                # 累加计算订单商品的数目和总价格
                amount = sku.price * count
                total_count += count
                total_price += amount
                break

            # todo:更新订单信息表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        # except Exception:
        #     transaction.savepoint_rollback(save_id)  # 回滚到保存点
        # return JsonResponse({'res': 8, 'errmsg': '下单失败'})

        # 提交事务
        transaction.savepoint_commit(save_id)

        # todo:清除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        return JsonResponse({'res': 5, 'errmsg': '创建成功'})


class OrderPayView(View):
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except Exception:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 业务处理：使用python sdk调用支付宝的支付接口
        private_key_path = os.path.join(settings.BASE_DIR, r'apps/order/app_private_key.pem')
        public_key_path = os.path.join(settings.BASE_DIR, r'apps/order/alipay_public_key.pem')

        alipay = AliPay(
            appid='2021000116673816',  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_string=open(private_key_path).read(),
            alipay_public_key_string=open(public_key_path).read(),
            sign_type='RSA2',  # RSA  or  RSA2
            debug=True)  # 使用沙箱

        total_pay = order.total_price + order.transit_price
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=str(total_pay),
            subject='天天生鲜%s' % order_id,
            return_url=None,
            notify_url=None)
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        print('订单正在支付中...')
        return JsonResponse({'res': 4, 'pay_url': pay_url})


class CheckPayView(View):
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except Exception:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 业务处理：使用python sdk调用支付宝的支付接口
        private_key_path = os.path.join(settings.BASE_DIR, r'apps/order/app_private_key.pem')
        public_key_path = os.path.join(settings.BASE_DIR, r'apps/order/alipay_public_key.pem')

        alipay = AliPay(
            appid='2021000116673816',  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_string=open(private_key_path).read(),
            alipay_public_key_string=open(public_key_path).read(),
            sign_type='RSA2',  # RSA  or  RSA2
            debug=True)  # 使用沙箱
        # 调用支付宝的交易查询接口
        while True:
            response = alipay.api_alipay_trade_query(order_id)
            # response = {
            #         "trade_no": "2017032121001004070200176844",
            #         "code": "10000",
            #         "invoice_amount": "20.00",
            #         "open_id": "20880072506750308812798160715407",
            #         "fund_bill_list": [
            #             {
            #                 "amount": "20.00",
            #                 "fund_channel": "ALIPAYACCOUNT"
            #             }
            #         ],
            #         "buyer_logon_id": "csq***@sandbox.com",
            #         "send_pay_date": "2017-03-21 13:29:17",
            #         "receipt_amount": "20.00",
            #         "out_trade_no": "out_trade_no15",
            #         "buyer_pay_amount": "20.00",
            #         "buyer_user_id": "2088102169481075",
            #         "msg": "Success",
            #         "point_amount": "0.00",
            #         "trade_status": "TRADE_SUCCESS",
            #         "total_amount": "20.00"}
            code = response.get('code')
            if code == '10000' and response.get('trade_status') == 'TRADE_SUCCESS':
                print('支付成功.............')
                # 获取支付宝交易号
                trade_no = response.get('trade_no')
                print('trade_no', trade_no)
                # 更新订单状态
                order.trade_no = trade_no
                print('更新订单')
                order.order_status = 4  # 待评价
                print('待评价')
                order.save()
                print('--------------------------->支付完毕')
                return JsonResponse({'res': 3, 'message': '支付成功'})
            elif code == '40004' or (code == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY'):
                print('等待买家付款...')
                # 等待买家付款
                import time
                time.sleep(2)
                continue
            else:
                # 支付出错
                return JsonResponse({'res': 4, 'errmsg': '支付失败'})


















