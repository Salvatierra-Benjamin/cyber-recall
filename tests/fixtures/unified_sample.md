# PreSecurity - TryHackMe (Unified Notes)

## Table of Contents

- Module 1
- Module 2

## Module 1 - Introduction to Cyber Security

### Module 1: Introduction to Cybersecurity

##### Active Recall Check

1. **What is the fundamental difference between Offensive and Defensive Security?**
    - *Answer:* Offensive security simulates attacks to find vulnerabilities, while defensive security monitors and blocks attackers.
2. **What is the purpose of tools like DirBuster or dirb?**
    - *Answer:* They discover hidden directories and files on a web server via brute-force attacks.

---

## Module 5 - Network Fundamentals

### What is Networking?

#### 5. Active Recall & Self-Assessment

**5.1. What is the difference between a private network and a public network?**

- **Answer:** A private network is a localized collection of connected devices, whereas a public network interconnects many private networks globally.

**5.2. What is the name of the function used to display text on the screen?**`print()`

**5.3. Why must applications rely on System Calls rather than accessing hardware directly?**
If applications had direct access, a malicious app could overwrite critical system memory.

### Packets & Frames

#### 5. Active Recall & Self-Assessment

**5.1. What is the fundamental difference between a Packet and a Frame?**

> **Answer:** A Packet operates at OSI Layer 3 and contains IP addressing information.
>

**5.2. Why do routers enforce a Time to Live (TTL) field?**
The TTL field acts as an expiry counter decremented at each router hop.

### Intro to LAN

#### 5. Active Recall & Self-Assessment

- **5.1. Question:** What is the core functional difference between a Switch and a Router?
    - **Answer:** A Switch connects devices within the same local network, whereas a Router connects different networks.

### Database SQL Basics

#### 5. Active Recall & Self-Assessment

**5.3. Write a SQL query that retrieves the `drink` and `price` columns.**

- **Answer:**

    ```sql
    SELECT drink, price
    FROM Orders
    WHERE drink = 'Coffee'
    ORDER BY price DESC;
    ```

    `DESC` sorts from most expensive to cheapest.

---

## Module 7 - Attacks and Defenses

### Cryptography Concepts

#### 5. Active Recall & Self-Assessment

##### 5.1. Why is it safe for cryptographic algorithms like AES to be completely public?

**Answer:** Under Kerckhoffs's Principle, security relies strictly on keeping the secret key private.

### Become a Defender

#### 5. Active Recall & Self-Assessment

**5.1. Why is an accurate asset inventory mandatory before deploying defensive tools?**

> **Answer:** You cannot protect, patch, or monitor systems you do not know exist.
>

Explore how independent Defense in Depth layers interact with real-world attack scenarios:

---

## Module 2 - Computer fundamentals

### Computer types

#### 5. Active Recall & Self-Assessment

**5.1. What is the defining difference between an IoT device and an Embedded computer?**
Connectivity. IoT devices connect to a network, while embedded computers operate offline.
