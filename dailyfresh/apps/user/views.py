from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from django.http import HttpResponse
from django.conf import settings
# from django.core.mail import send_mail
from celery_tasks.tasks import send_register_active_email
from django.contrib.auth import authenticate, login, logout
from utils.mixin import LoginRequiredMixin
from apps.user.models import User, Address
from django_redis import get_redis_connection
from apps.goods.models import GoodsSKU
from apps.order.models import OrderGoods, OrderInfo
from django.core.paginator import Paginator
import re


class RegisterView(View):
    def get(self, request):
        return render(request, 'register.html')

    def post(self, request):
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        cpassword = request.POST.get('cpwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 进行数据处理
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'register.html', {'errmsg': '数据不匹配'})

        if password != cpassword:
            # 两次密码不一致
            return render(request, 'register.html', {'errmsg': '密码不一致'})

        # 检验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})

        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})

        # 校验用户名是否重复
        try:
            user = User.objects.get(username=username)
        except Exception:
            # 用户名不存在
            user = None
        if user:
            return render(request, 'register.html', {'errmsg': '用户名已存在'})

        # 进行业务处理 ： 进行用户注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 创建加密对象，设置数据，加密
        ser = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        token = ser.dumps(info)  # 加密数据二进制
        token = token.decode('utf8')

        # 发送邮件
        # subject = '天天生鲜欢迎信息'  # 标题就是抬头
        # message = ''  # 邮件正文
        # sender = settings.EMAIL_FROM  # 发件人
        # receiver = [email]  # 收件人
        # html_message = '<h1>{0}, 欢迎您成为天天生鲜注册会员</h1>请点击下面链接激活您的账户<br/>' \
        #                '<a href="http://127.0.0.1:8000/user/active/{1}">激活链接{2}</a>'\
        #     .format(username, token, token)
        #
        # send_mail(subject, message, sender, receiver, html_message=html_message)

        send_register_active_email.delay(email, username, token)

        return redirect(reverse('goods:index'))


class ActiveView(View):
    def get(self, request, token):
        ser = Serializer(settings.SECRET_KEY, 3600)
        try:
            # 解密
            info = ser.loads(token)
            user_id = info['confirm']

            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()
            # 解密成功，跳转登录页面
            return redirect(reverse('user:login'))

        except SignatureExpired:
            return HttpResponse("激活链接已过期")


class LoginView(View):
    def get(self, request):
        # 判断是否记住了用户名
        if "username" in request.COOKIES:
            username = request.COOKIES.get('username')
            pwd = request.COOKIES.get('password')
            checked = 'checked'
        else:
            pwd = ""
            username = ""
            checked = ""
        res = {
            'username': username,
            "checked": checked,
            'pwd': pwd,
        }
        return render(request, 'login.html', res)

    def post(self, request):
        # 接收数据
        username = request.POST.get('username')
        pwd = request.POST.get('pwd')
        # 校验数据
        if not all([username, pwd]):
            return render(request, 'login.html', {'errmsg': '数据输入不完整'})
        # 业务处理
        user = authenticate(username=username, password=pwd)
        if user is not None:
            # 用户密码输入正确
            if user.is_active:
                # 用户已激活，记录用户的登录状态，还么有点击登录按钮呢
                login(request, user)
                next_url = request.GET.get('next', reverse('goods:index'))
                print("next_url: ", next_url)
                response = redirect(next_url)  # HttpResponse对象
                # response = redirect(reverse('goods:index'))
                # 判断用户的登录状态
                remember = request.POST.get('remember')
                if remember == "on":
                    # 记住用户名,设置session
                    response.set_cookie('username', username, max_age=7*24*3600)
                    response.set_cookie('password', pwd, max_age=7 * 24 * 3600)
                else:
                    response.delete_cookie('username')
                    response.delete_cookie('password')
                # 跳转首页
                return response
            else:
                return render(request, 'login.html', {'errmsg': '请激活链接'})
        else:
            return render(request, 'login.html', {'errmsg': '用户名密码错误'})
        # 返回应答


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect(reverse('goods:index'))


class UserInfoView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        address = Address.object.get_default_address(user)
        con = get_redis_connection('default')
        history_key = "history%d" % user.id
        sku_ids = con.lrange(history_key, 0, 4)  # 最近浏览的5个商品id
        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            print(goods.name)
            goods_li.append(goods)
        print(goods_li)
        res = {'page': 'user',
               'address': address,
               'goods_li': goods_li,
               }
        return render(request, 'user_center_info.html', res)


class UserOrderView(LoginRequiredMixin, View):
    def get(self, request, page):
        user = request.user
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')
        # 遍历获取订单商品的信息
        for order in orders:
            # 根据order_id查询订单商品信息
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)
            # 遍历order_skus计算商品的小计
            for order_sku in order_skus:
                amount = order_sku.count * order_sku.price
                order_sku.amount = amount
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            order.order_skus = order_skus
        paginator = Paginator(orders, 3)

        try:
            page = int(page)
        except Exception as e:
            page = 1
        if page > paginator.num_pages:  # 页码总数
            page = 1
        order_page = paginator.page(page)  # 返回当前页的数据

        # 进行页面的控制，页面上最多显示5个页码
        # 1.总页数小于5页，页面上显示所有页码
        # 2.如果当前页是前3页，显示1-5页
        # 3.如果当前页是后3页，显示后5页
        # 4.其它情况，显示  当前页的前2页，当前页，当前页后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        context = {'page': 'order',
                   'order_page': order_page,
                   'pages': pages}
        return render(request, 'user_center_order.html', context)


class AddressView(LoginRequiredMixin, View):
    def get(self, request):

        user = request.user
        # try:
        #     address = Address.object.get(user=user, is_default=True)
        # except Address.object.DoesNotExist:
        #     address = None

        address = Address.object.get_default_address(user)
        res = {'page': 'address',
               "address": address,
               }
        return render(request, 'user_center_site.html', res)

    def post(self, request):
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        phone = request.POST.get('phone')
        zip_code = request.POST.get("zip_code")
        if not all([receiver, addr, phone]):
            return render(request, "user_center_site.html", {'errmsg': '数据不完整'})

        if not re.match(r'1[3|4|5|7|8][0-9]{9}$', phone):
            return render(request, "user_center_site.html", {'errmsg': '手机号错误'})

        user = request.user

        # try:
        #     address = Address.object.get(user=user, is_default=True)
        # except Address.object.DoesNotExist:
        #     address = None

        address = Address.object.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        Address.object.create(user=user,
                              receiver=receiver,
                              addr=addr,
                              zip_code=zip_code,
                              phone=phone,
                              is_default=is_default)
        return redirect(reverse('user:address'))


















