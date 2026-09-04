moved {
  from = aws_route53_record.api
  to   = aws_route53_record.api[0]
}

moved {
  from = aws_route53_record.www
  to   = aws_route53_record.www[0]
}

moved {
  from = aws_route53_record.apex_a
  to   = aws_route53_record.apex_a[0]
}

moved {
  from = aws_acm_certificate.www
  to   = aws_acm_certificate.www[0]
}

moved {
  from = aws_acm_certificate_validation.www
  to   = aws_acm_certificate_validation.www[0]
}

moved {
  from = aws_cloudfront_function.apex_redirect
  to   = aws_cloudfront_function.apex_redirect[0]
}
