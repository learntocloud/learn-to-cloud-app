import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const { getToken, userId } = await auth();
  
  if (!userId) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }
  
  const token = await getToken();
  
  try {
    const response = await fetch(`${API_URL}/api/certificates/${id}/svg`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    
    if (!response.ok) {
      return NextResponse.json(
        { detail: "Certificate not found" },
        { status: response.status }
      );
    }
    
    const svgContent = await response.text();
    
    return new NextResponse(svgContent, {
      headers: {
        "Content-Type": "image/svg+xml",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("Certificate SVG fetch error:", error);
    return NextResponse.json(
      { detail: "Failed to fetch certificate" },
      { status: 500 }
    );
  }
}
