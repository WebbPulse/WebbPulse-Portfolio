# ---------------------------------------------------------------------------
# Identity standard, milestone M1. The permanent thing.
#
# M0 was a throwaway spike that answered one question: does an API Gateway HTTP
# API JWT authorizer verify an RS256 token signed by a real KMS key, against a
# JWKS and a discovery document served by our own Lambda? It does. M0 has been
# retired and this file is what replaced it. The scope is exactly section 9.1's M1 row and
# no more: a signing key, the grants the identity function needs to use it, and
# the configuration that lets the function serve the two `.well-known` documents
# through webbpulse.identity's own router.
#
# WHAT IS DELIBERATELY NOT HERE.
#
#  - No aws_apigatewayv2_authorizer. Attaching the JWT authorizer to a route is
#    M2 and later, and section 2.5 records why it is not merely the next line of
#    Terraform: an HTTP API route takes one authorizer, the staging access gate
#    already occupies that slot on every route, and which of the three answers
#    in 2.5 to take is question Q3 in section 11, still open. Nothing here
#    forces that decision.
#  - No DynamoDB tables. Section 4.2's nine tables belong to the flows, and the
#    flows are M2 and later. 0.9.0's stores are interfaces with no route calling
#    them, so a table created now would be an empty table with a backup policy.
#  - No symmetric data key. That is TOTP envelope encryption at M4.
#  - No SES wiring. Email is M3.
#
# The one thing M1 does that M0 did not: the `.well-known` routes are not
# conditional. Under the spike they existed only when a staging only flag was
# on. Here they are permanent and unconditional in both environments, because from M1 on the discovery document and the JWKS are
# what this product publishes about itself rather than an experiment's exhaust.
# Section 3.4 is emphatic that both have to answer anonymously before an
# authorizer can be created at all, so having them already live and already
# outside the gate is precisely what makes M2's first apply an ordinary one.
# ---------------------------------------------------------------------------

locals {
  # The issuer, byte for byte, and the single definition of it.
  #
  # Section 3.4: this exact string is three things at once. It is the `iss`
  # claim the token service signs, the `issuer` member of the discovery
  # document, and, from M2, the `issuer` on the authorizer. A mismatch between
  # any two of them presents as every request being denied with nothing in any
  # log to say why, and a trailing slash is the classic way to produce one. So
  # it is derived once here and read from this local everywhere else.
  #
  # The `/api/auth` path is the standard's own shape (section 6.2:
  # `https://api.carmodpicker.com/api/auth`), and M0 confirmed API Gateway is
  # happy with a path on the issuer: it appends
  # `/.well-known/openid-configuration` to whatever it is given rather than
  # requiring the document at the origin root.
  #
  # Which means the path is not cosmetic. The documents answer under `/api/auth`
  # and not at the origin, because that is where API Gateway looks, and the
  # jwks_uri the discovery document advertises is built from this same string,
  # so it lands under the path too. apigateway.tf's route keys and the router's
  # mount point in app/composition/wiring.py both follow from this local, which
  # is what keeps the three of them from disagreeing.
  #
  # local.api_host rather than local.api_url. api_url is module.api.api_url,
  # which is the custom domain URL only when custom domains are on and the
  # execute-api endpoint otherwise; the issuer has to be a stable public
  # hostname that resolves and serves TLS from outside AWS, because API Gateway
  # fetches it from its own infrastructure. api_host is that hostname directly,
  # `api.webbpulse.com` or `api.staging.webbpulse.com`, and it does not change
  # shape with another flag.
  identity_issuer = "https://${local.api_host}/api/auth"

  # The audience, matched by the authorizer from M2 and carried as `aud` on
  # every token from now.
  #
  # Section 3.2's convention is `<product>-api`. The M0 spike used
  # `webbpulse-<env>` and left M1 to settle the convention, so this settles it
  # on the standard's shape.
  #
  # It carries the environment because a staging token must not be accepted by
  # production. The audience is the only claim that distinguishes them once the
  # issuer differs by hostname anyway, and having both differ is cheap.
  identity_audience = "webbpulse-portfolio-${var.environment}-api"

  # The signing key ARNs, as the JSON array IDENTITY_SIGNING_KEY_ARNS expects.
  #
  # Read from the module rather than built here. The module owns the keys now,
  # and `signing_key_arns` is ordered by its `active_signing_key` input and
  # never sorted, which is the same contract this local carried: the head signs
  # and every element is published in the JWKS. Section 3.5's rotation is two
  # applies against `signing_key_count` and `active_signing_key` rather than an
  # edit to a list here.
  identity_signing_key_arns = module.identity.signing_key_arns

  # The cookie and WebAuthn scope: the registrable domain, not the API host.
  #
  # Section 6.1 is explicit that rp_id cannot be changed later, because the RP
  # ID is hashed into every credential by the authenticator and is immutable for
  # that credential's life. Choosing the registrable domain rather than a host
  # is therefore close to irreversible, and it is the right default because it
  # lets `www.` and any future subdomain share credentials.
  #
  # local.domain is already exactly that: `webbpulse.com` in production and
  # `staging.webbpulse.com` in staging. A passkey registered against staging
  # will not work in production, which is correct behaviour rather than a
  # problem, and the standard says so in the same paragraph.
  #
  # Neither value is used by a route in 0.9.0. They are set now because the
  # composition root reads the whole settings object at startup, and a value
  # that only appears at the milestone that first reads it is a value nobody
  # reviews when it is cheap to change.
  identity_registrable_domain = local.domain

  # The two M3 strings: where identity email comes from, and which SES
  # configuration set it is sent through. `terraform/ses.tf` creates both and
  # explains why this repository had no SES before M3.
  #
  # BOTH ARE EMPTY WHEN CUSTOM DOMAINS ARE OFF, AND THAT IS THE SWITCH RATHER
  # THAN AN ACCIDENT. A domain identity is verified by DKIM records, and without
  # a hosted zone there is nowhere to write them, so an SES identity created in
  # that configuration would stay permanently unverified and every send would
  # fail. Empty here means `IDENTITY_EMAIL_FROM` is empty on the function, which
  # means `build_email_sender` returns `None`, which means the package declares
  # none of the four email routes. A deployment that cannot send email serves
  # the M1 documents and the six M2 flows and promises nothing it cannot do.
  #
  # `no-reply@` because nothing reads replies to these two messages. The bodies
  # point a reader at `IDENTITY_SUPPORT_EMAIL` for a reply that a person will
  # see, which is the honest arrangement: a `From` that silently discards mail
  # and a stated address that does not is better than one address that looks
  # monitored and is not.
  identity_email_from            = local.custom_domains_enabled ? "no-reply@${local.domain}" : ""
  identity_ses_configuration_set = local.custom_domains_enabled ? "${local.prefix}-identity" : ""
}

# ---------------------------------------------------------------------------
# The identity layer, from the shared platform module.
#
# This replaced three hand-written resources and four table definitions that
# lived in two files. What the module owns now:
#
#  - The RSA_2048 SIGN_VERIFY signing key, its alias, and the key policy that
#    grants the identity Lambda role kms:Sign and kms:GetPublicKey.
#  - The identity tables. Four of them, credentials, refresh-tokens,
#    login-attempts and identity-tokens, moved out of module.dynamodb; two more,
#    totp-factors and recovery-codes, were created for M4; and four more,
#    passkeys, webauthn-challenges, oauth-states and oauth-links, are created by
#    this change for M5 and M6.
#  - The two IAM role policies, identity-signing and identity-tables, on the
#    identity function's role.
#
# Every one of those is a `moved` block below rather than a create, so adopting
# the module changes no resource in AWS beyond the two metadata differences the
# PR body lists.
#
# The pin is 2.8, which added four tables to the module's default map and
# nothing else: M5's `passkeys` and `webauthn-challenges`, and M6's
# `oauth-states` and `oauth-links`. The release is additive in the strict
# sense, no input, output or existing resource changed, so the bump itself
# contributes no diff and the four tables reach this workspace only because
# they are written into the `tables` map below.
#
# THIS CHANGE IS THE OTHER HALF FOR M6: the backend adopts webbpulse 0.14.0 and
# mounts the five OAuth routes, so `oauth-states` and `oauth-links` are created
# and read. The two M5 tables are created in the same apply and stay empty; the
# note in the map below says why that is the cheaper order.
#
# OAUTH IS INERT UNTIL A CLIENT ID EXISTS, and that is the property this change
# is built around rather than a caveat on it. `var.oauth_google_client_id` and
# `var.oauth_github_client_id` both default to "", the package's
# `OAuthService.enabled_providers()` counts a provider only when it carries a
# client id, and `build_identity_router` declares no OAuth route when that list
# is empty. So this applies into an environment with no OAuth apps registered,
# creates the two tables, sets two empty environment variables, and changes the
# served API not at all. Registering the apps and setting the HCP variables is
# a later, separate change with no code in it; docs/identity-cutover.md lists
# exactly what the owner has to create.
#
# The tables have to be listed rather than inherited. `tables` is passed
# explicitly, which replaces the module's default map wholesale rather than
# merging with it, so the two entries the module gained in 2.7.0 are absent from
# this workspace until they are written out below. That is why a plan against
# 2.7 showed no new tables when PR 164 applied.
#
# WHAT IS DELIBERATELY NOT PASSED.
#
# `http_api_id` stays unset, so no aws_apigatewayv2_authorizer is created here.
# An HTTP API route takes one authorizer and in staging the access gate already
# occupies that slot on every route, so which of section 2.5's three answers to
# take is still open and nothing here forces it. Leaving http_api_id null also
# leaves terraform_data.discovery_document_ready uncreated.
#
# The rotation inputs are left at their defaults, one key at index zero, which
# is exactly the single key state this environment is in. Section 3.5's rotation
# becomes two applies against signing_key_count and active_signing_key rather
# than an edit to a list of ARNs.
#
# ON TAGS, WHICH IS THE ONE PLACE THE MODULE'S SHAPE COSTS SOMETHING.
#
# `tags` and `name_tag` are module wide: they reach the signing key and the four
# tables alike, and there is no per-resource tag input. The hand-written key
# carries Name, Component and Milestone; the four tables carry none, because
# module.dynamodb was called with neither `tags` nor `name_tag`. No setting of
# these two inputs keeps both. Reproducing the key's tags is the option taken,
# because it keeps the key, the one resource whose tags exist today, byte
# identical, and the cost is three tags added to four tables. A tag addition is
# metadata: it is an in-place update, it replaces nothing, and it loses no data.
# The PR body lists all four addresses.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# M6's two OAuth client ids, and why they are variables with an empty default.
#
# A client id is not a secret. It travels in the authorization URL in the user's
# own browser on every sign in, so hiding it buys nothing, and the control that
# actually bounds what an attacker can do with one is the redirect URI allow
# list registered with the provider plus the client secret held at the token
# exchange. Both of those are elsewhere: the allow list is registered with
# Google and GitHub and re-checked by the package against
# `IDENTITY_OAUTH_REDIRECT_URIS` below, and the secret is a key of the
# `webbpulse-<env>/app` Secrets Manager secret. So these two are ordinary
# Terraform variables rendered into the function's environment rather than
# secret material.
#
# BOTH DEFAULT TO EMPTY, AND EMPTY IS THE OFF SWITCH RATHER THAN A
# MISCONFIGURATION. This is the same arrangement `IDENTITY_EMAIL_FROM` already
# uses for the four M3 email routes, for the same reason. The package's
# `OAuthService.enabled_providers()` counts a provider only when it carries a
# client id, and `build_identity_router` declares no OAuth route when that list
# comes back empty, so a deployment with neither id set serves exactly the
# routes it served before this change. A route that could only ever answer 503
# because nobody registered an OAuth app is worse than a route that is not in
# the OpenAPI document at all.
#
# That is what makes this change safe to apply before the owner has created
# anything. The tables exist, the variables are empty, no route is declared, and
# switching a provider on later is one HCP variable, one secret key and a
# redeploy with no Terraform edit in it.
#
# The provider names are fixed by the package: `IdentitySettings.oauth_providers`
# is a `Literal["google", "github"]`, so there is no third id to add here
# without a package release first.
# ---------------------------------------------------------------------------

variable "oauth_google_client_id" {
  description = "Google OAuth client id for identity M6 sign in, from the OAuth client the owner creates in the Google Cloud console. Empty means Google sign in is off and the package declares no OAuth route for it. Not a secret: it travels in the authorization URL in the user's browser. The matching secret is the `oauth_google_client_secret` key of the webbpulse-<env>/app secret."
  type        = string
  default     = ""
}

variable "oauth_github_client_id" {
  description = "GitHub OAuth client id for identity M6 sign in, from the OAuth app the owner creates in GitHub developer settings. Empty means GitHub sign in is off and the package declares no OAuth route for it. Not a secret, on the same reasoning as the Google id. The matching secret is the `oauth_github_client_secret` key of the webbpulse-<env>/app secret."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# M5's two passkey switches, and why each is a variable rather than a literal.
#
# THE PACKAGE DEFAULTS BOTH OF THESE TO TRUE AND THIS PRODUCT SHIPS BOTH FALSE.
# That inversion is the whole of what keeps this adoption inert, so it is worth
# stating plainly: an omitted variable here is not a no-op, it mounts seven
# routes. `IdentitySettings` defaults them on because the standard treats the
# baseline as mandatory and the flags exist to stage a rollout rather than to
# opt out permanently. Staging a rollout is exactly what this is.
#
# The two are separate switches because they are two different decisions.
#
# `passkeys_enabled` is the rollout step. With it true, all five management
# routes mount and a user can enrol, list, rename and delete a passkey. It waits
# on the frontend: `@webbpulse/auth` 0.8.0 is what calls
# `navigator.credentials.create`, and until it exists a mounted route is a route
# nothing calls and one a curious client could enrol a credential against, under
# an rp_id that is immutable for that credential's life.
#
# `passkeys_passwordless` is a policy decision and outlives the rollout. With it
# false and `passkeys_enabled` true, both `/login/passkey/*` routes refuse and a
# passkey is a managed credential and a second factor but not an entry point.
# With it true a passkey is a way into the account with no password at all. The
# package makes that safe rather than right: `POST /login/passkey/options`
# answers any input, including an unknown address, returning a challenge and an
# empty `allowCredentials` so an anonymous route does not become an account
# oracle. Whether a single administrator product wants a passwordless entry
# point is the owner's call, and it stays false until they make it.
#
# So the ordinary sequence is two separate HCP variable changes with a redeploy
# each, not one. docs/identity-cutover.md carries it.
# ---------------------------------------------------------------------------

variable "passkeys_enabled" {
  description = "Whether identity M5's passkey routes are declared. False, the shipping default, mounts none of the seven and leaves the served API identical to M6's. The package's own default is true, so this is set explicitly rather than omitted: an unset value here would mount routes the frontend has no code for. Turning it on needs @webbpulse/auth 0.8.0 on the frontend first."
  type        = bool
  default     = false
}

variable "passkeys_passwordless" {
  description = "Whether a passkey is an entry point as well as a credential. False, the shipping default, refuses both /login/passkey routes, so a passkey can be enrolled and managed and used as a second factor but cannot sign anybody in on its own. Independent of passkeys_enabled and stays off until the owner decides a passwordless sign in is wanted; the package's own default is true."
  type        = bool
  default     = false
}

variable "identity_rp_name" {
  description = "The WebAuthn Relying Party name, which is the product name a browser and an authenticator show the user during a passkey ceremony. Unlike rp_id this is a display string with no security meaning and can be changed at any time without invalidating a credential. Defaults to the value IDENTITY_RP_NAME already carries, so introducing this variable changes no environment."
  type        = string
  default     = "WebbPulse Portfolio"
}

locals {
  # The redirect URI allow list, as the JSON array IDENTITY_OAUTH_REDIRECT_URIS
  # expects.
  #
  # The package matches a requested `redirect_uri` against this list BY EXACT
  # STRING EQUALITY and never by prefix, and its own docstring gives the reason:
  # a prefix check on `https://app.example.com` also admits
  # `https://app.example.com.attacker.test`, which is a different registrable
  # domain that the provider will happily deliver a live authorization code to.
  # An unchecked redirect URI is a code exfiltration primitive rather than an
  # ordinary open redirect.
  #
  # One entry, and it is the package's own default anyway: `<issuer>/oauth/callback`,
  # which for this product is https://<api host>/api/auth/oauth/callback. Setting
  # it explicitly rather than leaving the list empty is worth the line, because
  # the string that has to be registered with Google and with GitHub is then
  # visible in the plan and in the console instead of being derived inside the
  # package, and this is exactly the value that a reviewer has to be able to
  # compare against what is registered with the provider.
  #
  # It is built from local.identity_issuer, the same local the `iss` claim, the
  # discovery document and the authorizer are all built from, so the callback
  # the package will accept and the callback it advertises cannot disagree.
  identity_oauth_redirect_uris = jsonencode(["${local.identity_issuer}/oauth/callback"])

  # M5's WebAuthn origin allow list, as the JSON array IDENTITY_WEBAUTHN_ORIGINS
  # expects. A JSON array rather than a bare string because
  # `IdentitySettings.webauthn_origins` is a list field and the class refuses
  # comma separated values for those, the same rule the redirect URIs above and
  # IDENTITY_SIGNING_KEY_ARNS both follow.
  #
  # THE ORIGIN CHECK IS THE WHOLE OF WHAT MAKES A PASSKEY PHISHING RESISTANT,
  # which is why the package requires this rather than defaulting it and raises
  # naming the variable when it is empty. An assertion carries the origin the
  # browser was actually on, and comparing it against this list is what stops a
  # credential enrolled on the real site from being usable on a lookalike. An
  # empty list makes that comparison vacuous.
  #
  # An origin, not a URL with a path: scheme, host and port only, which is what
  # the browser puts in `clientDataJSON`. It is built from local.domain, the
  # same local IDENTITY_FRONTEND_BASE_URL above is built from, so the origin a
  # browser sends and the origin a ceremony checks cannot drift apart. One entry,
  # because this product serves its frontend from one host per environment.
  #
  # This is the apex domain rather than the API host on purpose. The ceremony
  # happens in the page the user is looking at, which is the frontend, and the
  # API host only ever receives the already signed result.
  identity_webauthn_origins = jsonencode(["https://${local.domain}"])
}

module "identity" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/identity"
  version = "~> 2.8"

  name_prefix        = local.prefix
  issuer             = local.identity_issuer
  audience           = local.identity_audience
  registrable_domain = local.identity_registrable_domain

  identity_role_name = module.lambda_domain["identity"].role_id
  identity_role_arn  = module.lambda_domain["identity"].role_arn

  # Reproduces the tags the hand-written key carries so the key itself is a pure
  # move. See the tag note above for what this costs the four tables.
  tags = {
    Component = "identity"
    Milestone = "M1"
  }
  name_tag = true

  # The same pair module.dynamodb is called with, so the three tables that had
  # continuous backups keep them and login-attempts, which the module's own
  # default map already sets to false, keeps not having them. identity-tokens
  # overrides it to false below for the reason dynamodb.tf gave: restoring a
  # consumed single-use link to its unconsumed state is the one thing the
  # single-use guarantee exists to prevent.
  point_in_time_recovery = true
  deletion_protection    = var.environment == "production"

  # The actions the identity role gets on the four tables, matched to what
  # aws_iam_role_policy.lambda_domain["identity"] granted them before this
  # change rather than left at the module's shorter default.
  #
  # The module's default drops Scan, DescribeTable and ConditionCheckItem, and
  # dropping a permission is a behaviour change rather than a refactor. This is
  # the one part of the adoption that is not a state move: the grant was one
  # statement inside the `identity-runtime` policy and becomes its own
  # `identity-tables` policy on the same role, so it is an add here and a
  # narrowing of the existing policy there. Matching the action list keeps the
  # role's effective permissions on these four tables identical across that
  # split, which is what makes the split safe to make in one change. Narrowing
  # to the module's default is a separate decision with its own review.
  table_policy_actions = local.dynamodb_write_actions

  # THE WHOLE MAP, BECAUSE PASSING `tables` REPLACES THE DEFAULT RATHER THAN
  # MERGING WITH IT. Every entry below is byte identical to the module's own
  # default for that key, which is itself copied from `webbpulse.identity.storage`
  # and `webbpulse.identity.lockout`, with two deliberate exceptions:
  # identity-tokens turns point in time recovery off, and login-attempts restates
  # the false the default map already carries.
  #
  # A key omitted here is a table that does not exist, not a table that takes a
  # default, and for the four M2 and M3 tables that would be a destroy. That is
  # the reason the two M4 entries at the bottom have to be written out at all.
  tables = {
    credentials = {
      attributes = [
        { name = "user_id", type = "S" },
        { name = "credential_type", type = "S" },
      ]
      hash_key  = "user_id"
      range_key = "credential_type"
    }

    "refresh-tokens" = {
      attributes = [
        { name = "token_hash", type = "S" },
        { name = "family_id", type = "S" },
        { name = "generation", type = "N" },
      ]
      hash_key = "token_hash"
      global_secondary_indexes = [
        {
          name            = "family_id-generation-index"
          hash_key        = "family_id"
          range_key       = "generation"
          projection_type = "ALL"
        },
      ]
      ttl_attribute = "expires_at"
    }

    "login-attempts" = {
      attributes = [
        { name = "identity_key", type = "S" },
        { name = "attempted_at", type = "S" },
      ]
      hash_key               = "identity_key"
      range_key              = "attempted_at"
      ttl_attribute          = "expires_at"
      point_in_time_recovery = false
    }

    "identity-tokens" = {
      attributes             = [{ name = "token_hash", type = "S" }]
      hash_key               = "token_hash"
      ttl_attribute          = "expires_at"
      point_in_time_recovery = false
    }

    # M4's two tables, which are creates rather than moves: nothing in this
    # workspace has ever had them, because identity.tf passed `tables`
    # explicitly and the module's default map is therefore not what is in
    # effect. Both are restated here byte for byte from that default map, which
    # is itself copied from `webbpulse.identity.storage`, so the key schemas the
    # store writes and the key schemas DynamoDB enforces are the same strings.
    #
    # NEITHER HAS A TTL, AND NEITHER EVER WILL. Section 4.1's rule is at its
    # sharpest here. An expiring refresh token costs a user one extra sign in; a
    # TOTP factor or a recovery code deleted on DynamoDB's own reclaim schedule
    # costs them the account, silently and with the paper codes in their hand
    # still looking valid. The rows are deleted explicitly, by a user disabling
    # TOTP or by a regeneration replacing a set, and never on a clock.
    #
    # Both take the module wide `point_in_time_recovery = true` above rather
    # than overriding it, and that is the right default rather than an omission:
    # these hold user state that cannot be reconstructed. A restored TOTP seed
    # is the authenticator the user still has in their pocket, and a restored
    # recovery code set is the sheet they printed. `login-attempts` overrides to
    # false because a failure counter has nothing worth restoring, and
    # `identity-tokens` because restoring a consumed single-use link to its
    # unconsumed state is the one thing single use exists to prevent. Neither
    # argument applies to either table below.
    #
    # The seed is not stored in the clear, and none of that reaches this
    # schema. `webbpulse.identity.crypto` seals it under a data key minted from
    # the envelope key this same module creates, and the three envelope fields
    # are ordinary non-key attributes that DynamoDB neither indexes nor knows
    # about.
    "totp-factors" = {
      attributes = [{ name = "user_id", type = "S" }]
      hash_key   = "user_id"
    }

    "recovery-codes" = {
      attributes = [
        { name = "user_id", type = "S" },
        { name = "code_hash", type = "S" },
      ]
      hash_key  = "user_id"
      range_key = "code_hash"
    }

    # ------------------------------------------------------------------
    # M5's two tables and M6's two, all four creates for the same reason
    # the M4 pair above were: this call passes `tables` explicitly, so the
    # module's default map is not what is in effect and an entry the module
    # gained in 2.8.0 does not reach this workspace until it is written out
    # here. Each block below is byte identical to the module's own default
    # for that key, which is itself copied from `webbpulse.identity.storage`,
    # so the key schemas the store writes and the key schemas DynamoDB
    # enforces are the same strings.
    #
    # THE TWO M5 TABLES ARE CREATED AHEAD OF THE CODE THAT READS THEM, and
    # that is deliberate rather than an oversight. This change adopts
    # webbpulse 0.14.0, which is M6 only: the backend mounts no passkey route
    # and `IdentityStores` is given no passkey store, so `passkeys` and
    # `webauthn-challenges` sit empty until M5 is adopted. Creating them now
    # costs nothing on PAY_PER_REQUEST, keeps the module pin and the table
    # set in step at one version each, and means M5's adoption is a backend
    # change with no apply in front of it. An empty table is cheaper than a
    # second row-cut.
    # ------------------------------------------------------------------

    # M5. Hash user_id, range credential_id, with one index the other way
    # round. The primary key is that way because the credential management
    # page reads its own writes, and a consistent read is only available on
    # the base table; `credential_id-index` serves the login lookup, which
    # goes from a credential id to its owner and tolerates the index's
    # eventual consistency, because a credential written by an already
    # authenticated request is not one somebody is signing in with in the
    # same instant.
    #
    # The index name is a literal in the package, PASSKEY_CREDENTIAL_INDEX in
    # storage.py, so a rename here is a failed Query on the login path rather
    # than a plan diff. Projection is ALL because the login path reads the
    # stored public key and the sign count straight off the index, and
    # KEYS_ONLY would buy a second read on every sign in.
    #
    # NO TTL, EVER, on the rule totp-factors and recovery-codes already
    # follow. A passkey is a second factor, or the only factor, and one that
    # vanishes on DynamoDB's reclaim schedule is a credential removed from an
    # account silently. It goes when its owner removes it.
    passkeys = {
      attributes = [
        { name = "user_id", type = "S" },
        { name = "credential_id", type = "S" },
      ]
      hash_key  = "user_id"
      range_key = "credential_id"
      global_secondary_indexes = [
        {
          name            = "credential_id-index"
          hash_key        = "credential_id"
          projection_type = "ALL"
        },
      ]
    }

    # M5. Hash challenge_id, no range, no index, and one of the two tables in
    # this map whose rows are meant to disappear.
    #
    # A WebAuthn challenge is a row rather than a signed token because
    # unreplayability is a claim about state and a token cannot make it: a JWT
    # verifies exactly as well the second time as the first. The row is
    # written when options are generated, deleted when it is consumed, and
    # refused past its deadline whether or not DynamoDB has got round to
    # reclaiming it, so the TTL here is storage reclamation and never access
    # control. Pointing it at another attribute breaks nothing visibly and
    # grows the table forever, which is why `expires_at` is contract.
    "webauthn-challenges" = {
      attributes    = [{ name = "challenge_id", type = "S" }]
      hash_key      = "challenge_id"
      ttl_attribute = "expires_at"
    }

    # M6. Hash state, no range, no index, TTL on expires_at. The OAuth
    # analogue of webauthn-challenges and a row for the same reason: a state
    # binds a callback to the request that started it, and it is spent by a
    # conditional DeleteItem with ReturnValues=ALL_OLD, so it is single use
    # even under a concurrent replay. Expiry is re-checked on every read, so
    # an unreclaimed row is refused rather than accepted; ten minutes is the
    # package's deadline and is not configured from here.
    "oauth-states" = {
      attributes    = [{ name = "state", type = "S" }]
      hash_key      = "state"
      ttl_attribute = "expires_at"
    }

    # M6. Hash provider_subject ("<provider>#<subject>"), no range, with one
    # index the other way round on user_id.
    #
    # The primary key is the provider identity, which makes the uniqueness
    # constraint the primary key: attaching a provider is one conditional put
    # on attribute_not_exists(provider_subject), so a race resolves to one
    # winner with no read-then-write and no synthetic reservation rows. This
    # diverges from section 4.2 of the standard, which sketched a synthetic
    # id, and the package's 0.14.0 changelog says so explicitly.
    #
    # user_id-index answers "every link for this user", which both listing and
    # the last-method count in unlink need. A GSI rather than a second table
    # because two tables would need both rows written and deleted in step with
    # no cross-table transaction available, and a half-failed pair is an
    # orphaned link unlink cannot find. An index cannot disagree with its base
    # table. The price is eventual consistency, which the package buys out by
    # re-reading the base table by primary key before counting a candidate as
    # a remaining sign-in method.
    #
    # The index name is a literal in the package, OAUTH_LINK_USER_INDEX in
    # storage.py.
    #
    # NO TTL. A link is a sign-in method and may be the only one; it goes when
    # the user detaches the provider, which the package refuses when doing so
    # would remove the last way in.
    "oauth-links" = {
      attributes = [
        { name = "provider_subject", type = "S" },
        { name = "user_id", type = "S" },
      ]
      hash_key = "provider_subject"
      global_secondary_indexes = [
        {
          name            = "user_id-index"
          hash_key        = "user_id"
          projection_type = "ALL"
        },
      ]
    }
  }
}

# ---------------------------------------------------------------------------
# Outputs. The three strings a reviewer checks after an apply, and the two that
# M2's authorizer will be configured from.
# ---------------------------------------------------------------------------

output "identity_issuer" {
  description = "The identity issuer. Byte identical to the iss claim, to the issuer member of the discovery document, and from M2 to the JWT authorizer's configured issuer. Verify with: curl https://<api host>/.well-known/openid-configuration"
  value       = local.identity_issuer
}

output "identity_audience" {
  description = "The aud claim the identity function stamps on every access token, and the audience the M2 authorizer will require."
  value       = local.identity_audience
}

output "identity_signing_key_arns" {
  description = "The identity signing keys, active signer first. A single key today; a second entry is a rotation in progress per section 3.5 of the identity standard."
  value       = local.identity_signing_key_arns
}

output "identity_signing_key_alias" {
  description = "Alias of the active identity signing key. Points at the same key as the first entry of identity_signing_key_arns."
  value       = module.identity.signing_key_alias
}

output "identity_table_names" {
  description = "Logical name to physical name for the ten identity tables the module creates. The application derives the same strings from DYNAMODB_TABLE_PREFIX rather than reading this, so it is here for a reviewer checking an apply rather than for a consumer."
  value       = module.identity.table_names
}

# ---------------------------------------------------------------------------
# Adoption of the platform identity module. Every block below is a state move
# and none of them changes a resource in AWS.
#
# THE FIRST THREE ARE CHAINS, and the chaining is the point. The retired M0
# spike declared the key, the alias and the signing policy under a count, M1
# made them unconditional, and the three `moved` blocks that expressed that are
# still needed: a workspace that has never applied since M1 still has state at
# the indexed address.
# Terraform follows a chain of moves in one plan, so `[0]` to the bare address
# to the module address resolves in a single step, and dropping the first hop
# would destroy the signing key and create a new one under the same alias. That
# is the one mistake in this design with no recovery.
#
# The module's own resources use `count`, so each destination carries `[0]`.
# ---------------------------------------------------------------------------

moved {
  from = aws_kms_key.identity_signing[0]
  to   = aws_kms_key.identity_signing
}

moved {
  from = aws_kms_key.identity_signing
  to   = module.identity.aws_kms_key.identity_signing[0]
}

moved {
  from = aws_kms_alias.identity_signing[0]
  to   = aws_kms_alias.identity_signing
}

moved {
  from = aws_kms_alias.identity_signing
  to   = module.identity.aws_kms_alias.identity_signing[0]
}

moved {
  from = aws_iam_role_policy.identity_spike_signing[0]
  to   = aws_iam_role_policy.identity_signing
}

moved {
  from = aws_iam_role_policy.identity_signing
  to   = module.identity.aws_iam_role_policy.identity_signing[0]
}

# The four tables, out of module.dynamodb and into module.identity. Both calls
# build the physical name as "<name_prefix>-<key>" from the same local.prefix
# and both key their resource on the same logical name, so the name does not
# change and neither does anything DynamoDB stores.
#
# The two modules' table resources take the same arguments in the same shape,
# which is what makes this a move rather than a replace: `aws_dynamodb_table`
# forces a new resource only on `name`, `hash_key`, `range_key` and the
# attribute set, and all four are identical on both sides. The dynamodb-tables
# module also renders `stream_enabled`, `read_capacity` and `write_capacity`
# where the identity module does not, and every one of those is false or null on
# these four tables today, so none of them appears in the diff.

moved {
  from = module.dynamodb.aws_dynamodb_table.this["credentials"]
  to   = module.identity.aws_dynamodb_table.this["credentials"]
}

moved {
  from = module.dynamodb.aws_dynamodb_table.this["refresh-tokens"]
  to   = module.identity.aws_dynamodb_table.this["refresh-tokens"]
}

moved {
  from = module.dynamodb.aws_dynamodb_table.this["login-attempts"]
  to   = module.identity.aws_dynamodb_table.this["login-attempts"]
}

moved {
  from = module.dynamodb.aws_dynamodb_table.this["identity-tokens"]
  to   = module.identity.aws_dynamodb_table.this["identity-tokens"]
}
