# TFC injects AWS credentials automatically via dynamic provider credentials.
# No static keys needed here.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }

  # `awsApplication` is applied out-of-band by the myApplications tag-sync
  # task. Without this ignore, every plan would strip the tag and fight the
  # sync that re-adds it minutes later.
  ignore_tags {
    keys = ["awsApplication"]
  }
}

# ACM certificates for CloudFront must be provisioned in us-east-1 regardless
# of the primary deployment region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }

  ignore_tags {
    keys = ["awsApplication"]
  }
}

provider "aws" {
  alias  = "dns"
  region = var.aws_region

  dynamic "assume_role" {
    for_each = var.route53_write_role_arn == "" ? [] : [var.route53_write_role_arn]

    content {
      role_arn = assume_role.value
    }
  }

  default_tags {
    tags = local.common_tags
  }

  ignore_tags {
    keys = ["awsApplication"]
  }
}
