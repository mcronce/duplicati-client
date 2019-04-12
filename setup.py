import setuptools

setuptools.setup(
	name = 'duplicati_client',
	version = '1.0.0',
	author = 'Rune Henriksen',
	author_email = 'ruju@itu.dk',
	description = (
		'A library and CLI script for interacting with a Duplicati server'
	),
	packages = [
		'duplicati_client'
	],
	scripts = [
		'duc'
	]
)

