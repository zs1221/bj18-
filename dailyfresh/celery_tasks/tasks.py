from celery import Celery
from django.conf import settings
from django.core.mail import send_mail

# from django.shortcuts import render
from django.template import loader, RequestContext
from django_redis import get_redis_connection

import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh.settings")
django.setup()

from apps.goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner

app = Celery("celery_tasks.tasks", broker='redis://192.168.125.128:6379/8')


@app.task
def send_register_active_email(to_email, username, token):
    subject = '天天生鲜欢迎信息'  # 标题就是抬头
    message = ''  # 邮件正文
    sender = settings.EMAIL_FROM  # 发件人
    receiver = [to_email]  # 收件人
    html_message = '<h1>{0}, 欢迎您成为天天生鲜注册会员</h1>请点击下面链接激活您的账户<br/>' \
                   '<a href="http://127.0.0.1:8000/user/active/{1}">激活链接{2}</a>'\
        .format(username, token, token)
    send_mail(subject, message, sender, receiver, html_message=html_message)


@app.task
def generate_static_index_html():
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

    # 组织上下文

    context = {
        'types': types,
        'goods_banners': goods_banners,
        'promotion_banners': promotion_banners,
    }
    temp = loader.get_template('static_index.html')  # 加载模板文件
    # context = RequestContext(request, context)  # 定义模板上下文
    static_index_html = temp.render(context)  # 渲染模板后的内容
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')  # 生成页面静态文件
    with open(save_path, 'w') as f:
        f.write(static_index_html)



















