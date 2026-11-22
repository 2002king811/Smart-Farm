from django.urls import path

from . import views

urlpatterns = [
    # Auth (public unless noted)
    path("auth/signup", views.SignupView.as_view(), name="auth-signup"),
    path("auth/login", views.LoginView.as_view(), name="auth-login"),
    path("auth/refresh", views.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/password/forgot", views.ForgotPasswordView.as_view(), name="auth-password-forgot"),
    path("auth/password/reset", views.ResetPasswordView.as_view(), name="auth-password-reset"),
    path("auth/verify-email", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path(  # signed in
        "auth/verify-email/resend",
        views.ResendEmailVerificationView.as_view(),
        name="auth-verify-email-resend",
    ),
    path(
        "auth/verify-phone/send", views.SendPhoneCodeView.as_view(), name="auth-verify-phone-send"
    ),
    path("auth/verify-phone", views.VerifyPhoneView.as_view(), name="auth-verify-phone"),
    # The signed-in user
    path("me", views.MeView.as_view(), name="me"),
    path("me/photo", views.MePhotoView.as_view(), name="me-photo"),
    path("me/password", views.MePasswordView.as_view(), name="me-password"),
    path("me/farms", views.MyFarmsView.as_view(), name="me-farms"),
    # Farm settings (farm-scoped)
    path("farm", views.FarmView.as_view(), name="farm"),
    path("farm/logo", views.FarmLogoView.as_view(), name="farm-logo"),
    # Invitation links (public); must come before the router's invitations/{id}
    path("invitations/lookup", views.InvitationLookupView.as_view(), name="invitation-lookup"),
    path("invitations/accept", views.AcceptInvitationView.as_view(), name="invitation-accept"),
]
