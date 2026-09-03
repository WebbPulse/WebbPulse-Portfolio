moved {
  from = aws_vpc.main
  to   = aws_vpc.main[0]
}

moved {
  from = aws_subnet.public_a
  to   = aws_subnet.public_a[0]
}

moved {
  from = aws_subnet.public_b
  to   = aws_subnet.public_b[0]
}

moved {
  from = aws_internet_gateway.main
  to   = aws_internet_gateway.main[0]
}

moved {
  from = aws_route_table.public
  to   = aws_route_table.public[0]
}

moved {
  from = aws_route_table_association.public_a
  to   = aws_route_table_association.public_a[0]
}

moved {
  from = aws_route_table_association.public_b
  to   = aws_route_table_association.public_b[0]
}

moved {
  from = aws_security_group.rds
  to   = aws_security_group.rds[0]
}

moved {
  from = random_password.db
  to   = random_password.db[0]
}

moved {
  from = aws_db_subnet_group.main
  to   = aws_db_subnet_group.main[0]
}

moved {
  from = aws_db_instance.main
  to   = aws_db_instance.main[0]
}

moved {
  from = aws_ssm_parameter.database_url
  to   = aws_ssm_parameter.database_url[0]
}

moved {
  from = aws_ecr_repository.backend
  to   = aws_ecr_repository.backend[0]
}

moved {
  from = aws_ecr_lifecycle_policy.backend
  to   = aws_ecr_lifecycle_policy.backend[0]
}

moved {
  from = aws_iam_role.apprunner_ecr_access
  to   = aws_iam_role.apprunner_ecr_access[0]
}

moved {
  from = aws_iam_role_policy_attachment.apprunner_ecr_access
  to   = aws_iam_role_policy_attachment.apprunner_ecr_access[0]
}

moved {
  from = aws_iam_role.apprunner_instance
  to   = aws_iam_role.apprunner_instance[0]
}

moved {
  from = aws_iam_role_policy.apprunner_ssm
  to   = aws_iam_role_policy.apprunner_ssm[0]
}

moved {
  from = aws_apprunner_service.backend
  to   = aws_apprunner_service.backend[0]
}

moved {
  from = aws_apprunner_custom_domain_association.api
  to   = aws_apprunner_custom_domain_association.api[0]
}

moved {
  from = aws_route53_record.apprunner_cert_validation_0
  to   = aws_route53_record.apprunner_cert_validation_0[0]
}

moved {
  from = aws_route53_record.apprunner_cert_validation_1
  to   = aws_route53_record.apprunner_cert_validation_1[0]
}

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
