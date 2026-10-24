removed {
  from = module.company_site

  lifecycle {
    destroy = false
  }
}

removed {
  from = module.company_site_certificate

  lifecycle {
    destroy = false
  }
}

removed {
  from = module.company_site_dns

  lifecycle {
    destroy = false
  }
}

removed {
  from = module.company_site_gate

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_cloudfront_function.company_site

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_route53_record.company_site

  lifecycle {
    destroy = false
  }
}
