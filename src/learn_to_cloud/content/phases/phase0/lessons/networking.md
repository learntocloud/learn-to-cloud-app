Computer networking lets devices exchange data. A cloud application depends
on networks to reach users and to connect its own components.

## Follow a request

Imagine you open a website on your laptop. Your laptop connects to a local
network, such as your home Wi-Fi. A router forwards traffic between that
network and other networks. Across the internet, more routers help carry
the request toward the server. The server sends a response back.

The data travels in small pieces called packets. Each packet carries
address information that helps networks forward it. The receiving system
uses the arriving data to reconstruct the message.

## Find the service

An IP address identifies a network endpoint, like a device or service.
For example, `192.0.2.10` is an example IPv4 address. A service can use a
private address within a network or a public address reachable from the
internet when the network permits it.

People usually enter a name instead of an address. The Domain Name System
(DNS) looks up a name such as `example.com` and returns information that
can include an IP address. Your browser can then connect to that address.
DNS helps find a destination; it does not by itself guarantee that the
service is reachable.

A port identifies a service on a network endpoint. For example, a web
server commonly accepts HTTPS connections on port 443. Network rules can
allow or block traffic to an address and port.

## Use this in the cloud

Suppose a website deployed in the cloud does not load. Check one part of
the path at a time:

1. Does the domain name resolve to the intended address?
2. Is the application running and listening on the expected port?
3. Do the relevant network rules allow the connection?

Each answer narrows the search. An IP address, a DNS record, and a network
rule solve different parts of the problem.

## Check your understanding

Explain the path from a browser to a cloud web server. Include a DNS lookup,
an IP address, and a router. Then name one reason the connection might fail
after DNS returns an address.

## Go deeper

This resource is optional:

- [What is DNS?](https://www.cloudflare.com/learning/dns/what-is-dns/)
