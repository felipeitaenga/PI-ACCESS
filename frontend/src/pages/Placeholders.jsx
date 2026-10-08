import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Construction } from "lucide-react";

export function Placeholder({ title, subtitle, note }) {
  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} />
      <Card className="border-border bg-card p-12 text-center">
        <Construction className="mx-auto h-10 w-10 text-sky-400/60" />
        <p className="mt-4 text-sm text-muted-foreground max-w-md mx-auto">{note}</p>
      </Card>
    </div>
  );
}

export function Credentials() {
  return <Placeholder title="Credenciais" subtitle="Facial, cartão, QR code, PIN e placa (LPR)"
    note="O módulo de credenciais será implementado na próxima iteração. As credenciais (facial e cartão) já são geradas no seed e visíveis no detalhe de cada pessoa." />;
}
export function Visitors() {
  return <Placeholder title="Visitantes" subtitle="Pré-cadastro, agendamento e QR code temporário"
    note="O módulo de visitantes com envio de QR code por e-mail (Resend) e check-in/check-out será implementado na próxima iteração." />;
}
export function Rules() {
  return <Placeholder title="Regras de Acesso" subtitle="Zonas de tempo, feriados e níveis de acesso"
    note="O módulo de regras (zonas de tempo, níveis de acesso, anti-passback, intertravamento e dupla validação) será implementado na próxima iteração. Dados de exemplo já estão no seed." />;
}
