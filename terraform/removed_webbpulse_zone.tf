removed {
  from = aws_route53_zone.webbpulse

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_route53_record.mx

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_route53_record.spf

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_route53_record.dmarc

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_route53_record.dkim

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_route53domains_registered_domain.webbpulse

  lifecycle {
    destroy = false
  }
}
