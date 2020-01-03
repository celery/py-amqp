#This is a sample Image
FROM rabbitmq:latest

RUN mkdir /etc/rabbitmq/ca

RUN echo '-----BEGIN CERTIFICATE-----\n\
MIIDRzCCAi+gAwIBAgIJAMa1mrcNQtapMA0GCSqGSIb3DQEBCwUAMDExIDAeBgNV\n\
BAMMF1RMU0dlblNlbGZTaWduZWR0Um9vdENBMQ0wCwYDVQQHDAQkJCQkMCAXDTIw\n\
MDEwMzEyMDE0MFoYDzIxMTkxMjEwMTIwMTQwWjAxMSAwHgYDVQQDDBdUTFNHZW5T\n\
ZWxmU2lnbmVkdFJvb3RDQTENMAsGA1UEBwwEJCQkJDCCASIwDQYJKoZIhvcNAQEB\n\
BQADggEPADCCAQoCggEBAKdmOg5vtuZ5vNZmceToiVBlcFg9Y/xKNyCPBij6Wm5p\n\
mXbnsjO1PhjGr97r2cMLq5QMvGt+FBEIjeeULtWVCBY7vMc4ATEZ1S2PmmKnOSXJ\n\
MLMDIutznopZkyqt3gqWgXZDxxHIlIzJl0HirQmfeLm6eTOYyFoyFZV3CE2IeW4Y\n\
n1zYhgZgIrU7Yo3I7wY9Js5yLk4p3etByN5tlLL2sdCOjRRXWGbOh/kb8uiyotEd\n\
cxNThk0RQDugoEzaGYBU3bzDhKkm4v/v/xp/JxGLDl/e3heRMUbcw9d/0ujflouy\n\
OQ66SNYGLWFQpmhtyHjalKzL5UbTcof4BQltoo/W7xECAwEAAaNgMF4wCwYDVR0P\n\
BAQDAgEGMB0GA1UdDgQWBBTKOnbaptqaUCAiwtnwLcRTcbuRejAfBgNVHSMEGDAW\n\
gBTKOnbaptqaUCAiwtnwLcRTcbuRejAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3\n\
DQEBCwUAA4IBAQB1tJUR9zoQ98bOz1es91PxgIt8VYR8/r6uIRtYWTBi7fgDRaaR\n\
Glm6ZqOSXNlkacB6kjUzIyKJwGWnD9zU/06CH+ME1U497SVVhvtUEbdJb1COU+/5\n\
KavEHVINfc3tHD5Z5LJR3okEILAzBYkEcjYUECzBNYVi4l6PBSMSC2+RBKGqHkY7\n\
ApmD5batRghH5YtadiyF4h6bba/XSUqxzFcLKjKSyyds4ndvA1/yfl/7CrRtiZf0\n\
jw1pFl33/PTOhgi66MHa4uaKlL/hIjIlh4kJgJajqCN+TVU4Q6JNmSuIsq6rksSw\n\
Rd5baBZrik2NHALr/ZN2Wy0nXiQJ3p+F20+X\n\
-----END CERTIFICATE-----' > /etc/rabbitmq/ca/ca_certificate.pem

RUN echo '-----BEGIN CERTIFICATE-----\n\
MIIDjjCCAnagAwIBAgIBATANBgkqhkiG9w0BAQsFADAxMSAwHgYDVQQDDBdUTFNH\n\
ZW5TZWxmU2lnbmVkdFJvb3RDQTENMAsGA1UEBwwEJCQkJDAgFw0yMDAxMDMxMjAx\n\
NDFaGA8yMTE5MTIxMDEyMDE0MVowLzEcMBoGA1UEAwwTZXhhbXBsZS5leGFtcGxl\n\
LmNvbTEPMA0GA1UECgwGc2VydmVyMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB\n\
CgKCAQEAwlYnHfsXVhShuDPht5w9BgdEKDzjZtb+a0rvslg+9nYiHbFAZmAKDb69\n\
s0vMk55AtDdPVDxuoWawavvcZLuEVwEi4h51Ekc80trIC6oLy3hf3sLGl9Ru1zxG\n\
K+F46thhdcBdPZRxlJr5GMYLdXWtXiNtPZSJMLFfMespmZxNsMha2Uo8JZXKDZrO\n\
p7CChDQFjtdOyu/NesGO3mwGTLzI1MbldytkmQ6OR4cNXu1sEPU/zKG57oDtezFD\n\
t9TVMDIP6EWit4FXE3Yn8vQMz0tmgUNSR7CJDKIHO69u5BpWYYv4gTebWdHT7tRm\n\
eYgK7EyS0rETrzDf7+8xzyUVEyVonwIDAQABo4GwMIGtMAkGA1UdEwQCMAAwCwYD\n\
VR0PBAQDAgWgMBMGA1UdJQQMMAoGCCsGAQUFBwMBMD4GA1UdEQQ3MDWCE2V4YW1w\n\
bGUuZXhhbXBsZS5jb22CE2V4YW1wbGUuZXhhbXBsZS5jb22CCWxvY2FsaG9zdDAd\n\
BgNVHQ4EFgQUiS0qh+Ntvzm1MgDmH2allqc2jkIwHwYDVR0jBBgwFoAUyjp22qba\n\
mlAgIsLZ8C3EU3G7kXowDQYJKoZIhvcNAQELBQADggEBAAfePCF0JYEASi0LeDqv\n\
ZScEN2GsRB3nD1HY6jtM0EZE9quSZO+TLMO28XgiunQagrp+Y01yNim6LV+0FjfI\n\
jj+LusnlGD6xWmwHS4bg61RizAoFdKoEja6gEeeN5v+Ko+NNsu6aJFh0Mlf55j4n\n\
hHS/yQyUsiYasgdm/t14HjhpzRVOntzm0mf1JStVk1TrtSMxjOi51NZuNUUlxy7k\n\
dtDNdfUmVIJo+hOaIu+JumIn5DZ/KDzoaQntB1NpHtWW5IfgN5U+Cc9vI8CdCL1r\n\
GEZdciNkK6LcvoK/XeJmE/siGXz8ovBMvqBMVYjMNVlvcIr8gvEzFYxZQFXowNwK\n\
c0c=\n\
-----END CERTIFICATE-----' > /etc/rabbitmq/ca/server_certificate.pem

RUN echo '-----BEGIN RSA PRIVATE KEY-----\n\
MIIEpQIBAAKCAQEAwlYnHfsXVhShuDPht5w9BgdEKDzjZtb+a0rvslg+9nYiHbFA\n\
ZmAKDb69s0vMk55AtDdPVDxuoWawavvcZLuEVwEi4h51Ekc80trIC6oLy3hf3sLG\n\
l9Ru1zxGK+F46thhdcBdPZRxlJr5GMYLdXWtXiNtPZSJMLFfMespmZxNsMha2Uo8\n\
JZXKDZrOp7CChDQFjtdOyu/NesGO3mwGTLzI1MbldytkmQ6OR4cNXu1sEPU/zKG5\n\
7oDtezFDt9TVMDIP6EWit4FXE3Yn8vQMz0tmgUNSR7CJDKIHO69u5BpWYYv4gTeb\n\
WdHT7tRmeYgK7EyS0rETrzDf7+8xzyUVEyVonwIDAQABAoIBAQCRVcTjUwjcw4k+\n\
LO69Vgb9HyoFvaODIX4b12rzQbO0thxFgG3dIi3ioadVE3bnXw6cuFCHerpx0k5V\n\
dA4a93G9b4ga+xQqm0QNnLjGoGE5xchM2/WRTrmmFdmUr4ayeyhH25jfmMhojo2D\n\
zXh8W4lQQcZMq2z+EWhT+L6ftpkTfzOW3G7aUg7eYN/edQ+jJiD0CvCd5FyuIfxf\n\
RFLtp1A+DXzh05OqO6uaVrucdMKuYF8dawI75imoxYCLvpCeKdEsQ4h5yNsNTkZu\n\
InYZhZJ1YZfgj/P+2QwKjdMcdAOB4P1F/xdV1GkREHOgsznfFgfrod90/D0jcKyz\n\
iVgkY05hAoGBAPfmG3PtQbO126hvKcAB7JgztmWJ0HiLPP+fVCSJvbkp+0fnVNZ0\n\
Bxl8r2dLNIDFsdJIiNeI/u8umoJT0gFGXkJjYyW2hY32hqm7kTbQo91O0Crv34Wg\n\
Z66Kj2NZox7T53HxdTMIZI28qXDpHVm8Q7uW+6CgLcshABhwowxW42y7AoGBAMiv\n\
8w+4yzZJH37PWNOObe6hKXPvzWXDIKML3ENc3EPES+cxG4ke8+ltNZf6hgyvbbpf\n\
Fbs6Z14j5N3sfNxpuHp65O3MI3pF5kKAobjexg97GA3nuiyxQJ6/Z/hu1Dtt8hWU\n\
D7mWH7RwlnMFBpTC5A275dzoYfyC+qGW4xVDFQdtAoGBANbrJk3hGh8lwWRLy9Rt\n\
VqO14aIyUwzPGnk7twVebZ/Ep9f01PZ/7U/Ja4CQENq7iqkWvZyvZuYSb14iMWVt\n\
jnbcF68wiKVFYAZzWTg+tnI9y/gNsqn1IS6PbjTiF6u4Z2W/wq4VzqebMwNy90E/\n\
GTHfehQOCuWanKyTqqgeBFnVAoGBAJzJocqZo+GQdVO8KHh3oPk63cjfA4hKTvgy\n\
7u2N4ePruyUvH4UcMpEeqi1HI21LrR1a5f51XYaV4ltjRBVrXx4JX0tNHjaL3537\n\
It3s5a34jE1oyfHatVKQ1WipJZQcjHJBT5u9Zp2xDElmFsMoE8WLE8VnpA4EQkz2\n\
NglJdGdtAoGAPbBvhaW18wdy1jgzcQB84ODdXAZ6dPMXAhWcTQ8t2r4hKpfutMA9\n\
SGRMy+oEhSToMDPALn7EnQGJdGeZJjlXn8mLiqo1hHhfyFPK87EyAONHamZJQ3k7\n\
LdsBZMl5sYt+9dt5/CE38cU/VkS5pqueLT8c1RGBHnObLw7sU5XK2o8=\n\
-----END RSA PRIVATE KEY-----' > /etc/rabbitmq/ca/server_key.pem

RUN echo 'loopback_users = none\n\
listeners.ssl.default = 5671\n\
ssl_options.cacertfile = /etc/rabbitmq/ca/ca_certificate.pem\n\
ssl_options.certfile   = /etc/rabbitmq/ca/server_certificate.pem\n\
ssl_options.keyfile    = /etc/rabbitmq/ca/server_key.pem\n\
ssl_options.verify     = verify_peer\n\
ssl_options.fail_if_no_peer_cert = true' > /etc/rabbitmq/rabbitmq.conf
