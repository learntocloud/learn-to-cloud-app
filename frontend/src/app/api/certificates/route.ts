import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const { getToken, userId } = await auth();
  
  if (!userId) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }
  
  const token = await getToken();
  
  try {
    const body = await request.json();
    
    const response = await fetch(`${API_URL}/api/certificates`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }
    
    return NextResponse.json(data);
  } catch (error) {
    console.error("Certificate generation error:", error);
    return NextResponse.json(
      { detail: "Failed to generate certificate" },
      { status: 500 }
    );
  }
}
