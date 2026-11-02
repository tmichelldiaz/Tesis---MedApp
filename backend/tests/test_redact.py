from app.rag.redact import redact_pii


class TestRedactPii:
    def test_masks_labeled_name(self):
        assert redact_pii("Paciente: Juan Pérez Gómez") == "Paciente: [dato oculto]"

    def test_masks_labeled_cedula(self):
        assert redact_pii("C.C.: 1090456789") == "C.C.: [dato oculto]"
        assert redact_pii("Cédula de ciudadanía: 1.090.456.789") == "Cédula de ciudadanía: [dato oculto]"

    def test_masks_labeled_phone(self):
        assert redact_pii("Teléfono: 3001234567") == "Teléfono: [dato oculto]"

    def test_masks_labeled_address(self):
        assert redact_pii("Dirección: Calle 10 # 5-20") == "Dirección: [dato oculto]"

    def test_masks_bare_email_even_without_a_label(self):
        assert redact_pii("contacto: tania.diaz@example.com") == "contacto: [correo oculto]"

    def test_masks_a_bold_markdown_label_in_a_list_item(self):
        assert redact_pii("- **Nombre:** Juan Pérez Gómez") == "- **Nombre:** [dato oculto]"

    def test_leaves_clinical_content_untouched(self):
        md = "## Sangre\n\n| Examen | Resultado |\n|---|---|\n| Glucosa | 94 |\n\nControl en 3 meses."
        assert redact_pii(md) == md

    def test_leaves_a_bare_unlabeled_number_untouched(self):
        # Limitación conocida: sin etiqueta no hay forma de saber que es un
        # identificador y no un valor clínico.
        assert redact_pii("1090456789") == "1090456789"
