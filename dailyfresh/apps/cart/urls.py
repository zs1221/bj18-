from django.conf.urls import url
from apps.cart.views import CartAddView, CartInfoView, CartUpdateView, CartDeleteView
from apps.order.views import OrderPlaceView
urlpatterns = [
    url(r"^add$", CartAddView.as_view(), name='add'),
    url(r"^cart$", CartInfoView.as_view(), name='cart_show'),
    url(r"^delete$", CartDeleteView.as_view(), name='delete'),
    url(r"^update$", CartUpdateView.as_view(), name='update'),
    url(r"^place$", OrderPlaceView.as_view(), name='place'),
]
