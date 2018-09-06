:orphan:

.. _dynamodb_policy:

DynamoDB Policy
===============
In order for pypicloud to be able to access your DynamoDB tables, you may need to set
some policy options. The permissions required are:

* ``dynamodb:CreateTable``
* ``dynamodb:BatchWriteItem``
* ``dynamodb:BatchGetItem``
* ``dynamodb:PutItem``
* ``dynamodb:DescribeTable``
* ``dynamodb:ListTables``
* ``dynamodb:Scan``
* ``dynamodb:Query``
* ``dynamodb:UpdateItem``
* ``dynamodb:DeleteTable``

The following policy should work::

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:CreateTable",
                    "dynamodb:BatchWriteItem",
                    "dynamodb:BatchGetItem",
                    "dynamodb:PutItem",
                    "dynamodb:DescribeTable",
                    "dynamodb:ListTables",
                    "dynamodb:Scan",
                    "dynamodb:Query",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteTable"
                ],
                "Resource": "*"
            }
        ]
    }
