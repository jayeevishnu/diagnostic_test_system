from rest_framework.routers import DefaultRouter

from .views import CentreTestViewSet, DiagnosticCentreViewSet, DiagnosticTestViewSet

router = DefaultRouter()
router.include_root_view = False
router.register("tests", DiagnosticTestViewSet, basename="test")
router.register("centres", DiagnosticCentreViewSet, basename="centre")
router.register("centre-tests", CentreTestViewSet, basename="centre-test")

urlpatterns = router.urls
