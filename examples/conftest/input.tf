resource "aws_imaginary_resource" "this" {
  name = "this"
  instance_type = "r5.4xlarge"
  security_groups = ["12345", "45678"]
}

resource "aws_imaginary_resource" "that" {
  name = "that"
  instance_type = "t3.medium"
  
  ingress {
    port = 1234
    cidr = ["0.0.0.0/0"]
  }
}
